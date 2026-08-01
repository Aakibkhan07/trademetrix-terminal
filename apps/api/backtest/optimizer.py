"""Strategy parameter optimizer: grid search, walk-forward validation,
Monte Carlo bootstrap (trade-level), and one-factor-at-a-time sensitivity.

Design doc Phase 5.5:
- Grid: exhaustive product over param ranges, capped at 512 combos (error above).
- Walk-forward: candles split into `windows` folds; each fold's params are
  chosen by grid search on the PREVIOUS fold (train) and evaluated on the fold
  itself (test); results aggregated per fold.
- Monte Carlo: 2000 bootstrap paths over the base run's trade PnLs (with
  replacement, same length) → percentile bands + probability of profit.
- Sensitivity: OFAT ±20% around the base params for each parameter.
"""
from __future__ import annotations

import itertools
import logging
import random
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from backtest.manager import backtest_manager
from backtest.models import BacktestConfig, BacktestStatus

logger = logging.getLogger(__name__)

MAX_COMBOS = 512
MC_PATHS = 2000


class OptimizationSpec(BaseModel):
    strategy_type: str
    strategy_params: dict = Field(default_factory=dict)
    symbol: str = "NIFTY"
    exchange: str = "NSE"
    interval: str = "15m"
    days: int = 60
    initial_capital: float = 100000.0
    method: str = "grid"           # grid | walk_forward | monte_carlo | sensitivity
    param_ranges: dict[str, list] = Field(default_factory=dict)
    windows: int = 6
    mc_paths: int = MC_PATHS
    max_combos: int = MAX_COMBOS
    seed: int | None = None
    close_positions_on_end: bool = True


class ComboResult(BaseModel):
    params: dict = Field(default_factory=dict)
    metrics: dict = Field(default_factory=dict)
    error: str = ""


class OptimizationResult(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: str = BacktestStatus.RUNNING.value
    method: str = ""
    strategy_type: str = ""
    symbol: str = ""
    combos_total: int = 0
    combos_completed: int = 0
    results: list[ComboResult] = Field(default_factory=list)
    best: dict = Field(default_factory=dict)
    distribution: dict = Field(default_factory=dict)
    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str = ""
    error: str = ""


def _metrics_from_result(result) -> dict:
    return {
        "net_pnl": result.net_pnl,
        "return_pct": result.return_pct,
        "win_rate": result.win_rate,
        "total_trades": result.total_trades,
        "profit_factor": result.profit_factor,
        "max_drawdown_pct": result.max_drawdown_pct,
        "sharpe_ratio": result.sharpe_ratio,
        "sortino_ratio": result.sortino_ratio,
        "calmar_ratio": result.calmar_ratio,
        "expectancy": result.expectancy,
        "end_equity": result.end_equity,
    }


class BacktestOptimizer:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._runs: dict[str, OptimizationResult] = {}

    async def run(self, spec: OptimizationSpec) -> OptimizationResult:
        out = OptimizationResult(
            method=spec.method,
            strategy_type=spec.strategy_type,
            symbol=spec.symbol,
        )
        self._runs[out.run_id] = out
        try:
            if spec.method == "grid":
                await self._grid(spec, out)
            elif spec.method == "walk_forward":
                await self._walk_forward(spec, out)
            elif spec.method == "monte_carlo":
                await self._monte_carlo(spec, out)
            elif spec.method == "sensitivity":
                await self._sensitivity(spec, out)
            else:
                raise ValueError(f"Unknown optimization method: {spec.method}")
            out.status = BacktestStatus.COMPLETED.value
        except Exception as e:
            logger.exception("Optimization failed")
            out.status = BacktestStatus.FAILED.value
            out.error = str(e)
        out.completed_at = datetime.now(UTC).isoformat()
        return out

    def get(self, run_id: str) -> OptimizationResult | None:
        return self._runs.get(run_id)

    def _config(self, spec: OptimizationSpec, params: dict, slice_: tuple[int, int] | None = None) -> BacktestConfig:
        merged = {**spec.strategy_params, **params}
        return BacktestConfig(
            strategy_type=spec.strategy_type,
            strategy_params=merged,
            symbol=spec.symbol,
            exchange=spec.exchange,
            interval=spec.interval,
            days=spec.days,
            initial_capital=spec.initial_capital,
            close_positions_on_end=spec.close_positions_on_end,
            seed=spec.seed,
            candle_slice=slice_,
        )

    async def _run_combo(self, spec: OptimizationSpec, params: dict,
                         slice_: tuple[int, int] | None = None) -> ComboResult:
        result = await backtest_manager._fast_run(self._config(spec, params, slice_))
        if result.status == BacktestStatus.FAILED:
            return ComboResult(params=params, metrics={}, error=result.error)
        return ComboResult(params=params, metrics=_metrics_from_result(result))

    def _combos(self, spec: OptimizationSpec) -> list[dict]:
        ranges = {k: v for k, v in spec.param_ranges.items() if v}
        if not ranges:
            return [{}]
        keys = list(ranges.keys())
        combos = [dict(zip(keys, values)) for values in itertools.product(*(ranges[k] for k in keys))]
        if len(combos) > spec.max_combos:
            raise ValueError(
                f"Too many parameter combinations ({len(combos)} > {spec.max_combos})",
            )
        return combos

    def _best(self, out: OptimizationResult) -> None:
        scored = [r for r in out.results if r.metrics and not r.error]
        if not scored:
            return
        best = max(scored, key=lambda r: r.metrics.get("net_pnl", float("-inf")))
        out.best = {"params": best.params, "metrics": best.metrics}

    async def _grid(self, spec: OptimizationSpec, out: OptimizationResult) -> None:
        combos = self._combos(spec)
        out.combos_total = len(combos)
        for params in combos:
            out.results.append(await self._run_combo(spec, params))
            out.combos_completed += 1
        self._best(out)

    async def _walk_forward(self, spec: OptimizationSpec, out: OptimizationResult) -> None:
        if not spec.param_ranges:
            raise ValueError("walk_forward requires param_ranges")
        # probe total candle count with the base config
        probe = await backtest_manager._fast_run(self._config(spec, {}))
        if probe.status == BacktestStatus.FAILED:
            raise ValueError(f"Probe run failed: {probe.error}")
        total = probe.candles_analyzed
        if total < spec.windows * 2:
            raise ValueError("Not enough candles for walk-forward windows")

        fold = total // spec.windows
        combos = self._combos(spec)
        out.combos_total = spec.windows
        for i in range(spec.windows):
            test_slice = (i * fold, (i + 1) * fold if i < spec.windows - 1 else total)
            train_slice = (max(0, test_slice[0] - fold), test_slice[0])
            train_results = [
                await self._run_combo(spec, p, train_slice) for p in combos
            ]
            scored = [r for r in train_results if r.metrics]
            if not scored:
                out.results.append(ComboResult(
                    params={}, metrics={}, error="No train window results",
                ))
                out.combos_completed += 1
                continue
            best_train = max(scored, key=lambda r: r.metrics.get("net_pnl", float("-inf")))
            test = await self._run_combo(spec, best_train.params, test_slice)
            test.params = {"window": i, **best_train.params}
            out.results.append(test)
            out.combos_completed += 1
        self._best(out)

    async def _monte_carlo(self, spec: OptimizationSpec, out: OptimizationResult) -> None:
        base = await self._run_combo(spec, {})
        if base.error or not base.metrics:
            raise ValueError(f"Base run failed: {base.error or 'no metrics'}")
        # re-run base through _fast_run to capture trade PnLs
        result = await backtest_manager._fast_run(self._config(spec, {}))
        pnls = [t.pnl for t in result.trades]
        if not pnls:
            raise ValueError("Base run produced no trades for Monte Carlo")

        rng = random.Random(spec.seed)
        n = len(pnls)
        paths = []
        for _ in range(spec.mc_paths):
            paths.append(sum(rng.choice(pnls) for _ in range(n)))

        paths.sort()
        def pct(p: float) -> float:
            idx = min(len(paths) - 1, int(p / 100 * len(paths)))
            return round(paths[idx], 2)

        profitable = sum(1 for p in paths if p > 0) / len(paths) * 100
        out.combos_total = 1
        out.combos_completed = 1
        out.results = [base]
        out.best = {"params": {}, "metrics": base.metrics}
        out.distribution = {
            "paths": spec.mc_paths,
            "p5": pct(5),
            "p25": pct(25),
            "p50": pct(50),
            "p75": pct(75),
            "p95": pct(95),
            "probability_of_profit_pct": round(profitable, 2),
            "mean": round(sum(paths) / len(paths), 2),
        }

    async def _sensitivity(self, spec: OptimizationSpec, out: OptimizationResult) -> None:
        if not spec.param_ranges:
            raise ValueError("sensitivity requires param_ranges")
        base = await self._run_combo(spec, {})
        out.results.append(base)
        out.combos_total = 1 + 2 * len(spec.param_ranges)
        for param, values in spec.param_ranges.items():
            base_val = spec.strategy_params.get(param) or (values[0] if values else 0)
            for factor in (0.8, 1.2):
                try:
                    perturbed = float(base_val) * factor
                except (TypeError, ValueError):
                    continue
                combo = await self._run_combo(spec, {param: perturbed})
                combo.params = {param: perturbed, "base": base_val, "factor": factor}
                out.results.append(combo)
                out.combos_completed += 1
        out.combos_completed += 1
        self._best(out)


backtest_optimizer = BacktestOptimizer()
