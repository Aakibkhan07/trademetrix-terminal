"""Backtest risk simulation engine.

Replaces the LIVE risk dry-run for backtests. The live engine evaluated
backtest orders against LIVE account state (Supabase orders queries, Redis
kill switch, market-status checks) via ``risk_manager.evaluate(dry_run=True)``
and rejected every order (the ``risk_enabled=true -> 0 trades`` incident).

This module evaluates orders against the SIMULATED account only
(``BacktestBroker`` equity / cash / positions / realized P&L), so backtest
risk and live risk stay semantically aligned without live-state leakage.

Reuse: the shared Risk Engine vocabulary is used as-is — ``RiskConfig``
(extended with backtest-only knobs), ``RiskDecision``, ``RiskRuleType``.
Each simulated rule mirrors the live rule's thresholds and rejection
semantics (see risk/rules.py) but reads simulated state.

Simulated: position sizing (max_risk_per_trade_pct), max capital, max
exposure, max symbol exposure, max open positions, max quantity, max trades
per day, daily loss limit, daily profit target, max drawdown, circuit
breaker (halt after a hard-limit breach) and kill switch (simulation only).

NOT simulated (live/paper system rules, by design): broker authentication,
market-open validation, trading window, live margin API, broker
connectivity, OMS queue state, duplicate/cooldown/rate rules.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from backtest.models import RiskAnalytics, RiskCurvePoint, RiskRejection, RiskTimelinePoint
from risk.models import RiskConfig, RiskDecision, RiskRuleType

logger = logging.getLogger(__name__)

#: Sentinel risk_remaining: no daily-loss limit configured (unlimited budget).
NO_LIMIT = -1.0


class BacktestRiskConfig(RiskConfig):
    """Risk settings evaluated during a backtest run.

    Extends the shared RiskConfig with backtest-only knobs. All fields are
    defaulted; 0 / False / empty disables the corresponding rule:

    - ``max_risk_per_trade_pct``: per-trade notional risk cap (% of equity).
      Oversized opening orders are CLAMPED to the risk budget (position
      sizing), not rejected.
    - ``circuit_breaker``: after a hard-limit breach (daily loss / drawdown)
      all remaining orders are halted (simulated kill switch).
    """

    max_risk_per_trade_pct: float = 0.0
    circuit_breaker: bool = True


class BacktestRiskCheck(BaseModel):
    """Result of evaluating one backtest order against the simulation."""

    decision: RiskDecision = RiskDecision.APPROVED
    adjusted_quantity: int | None = None
    rule: str = ""
    reason: str = ""
    details: dict = Field(default_factory=dict)


def _default_overrides(initial_capital: float) -> dict:
    """Capital-derived institutional defaults.

    Guardrails are deliberately loose so a healthy strategy is unaffected
    (risk ON == risk OFF trade count) and hard limits bind only in genuinely
    bad runs — a run can never be reduced to zero trades by these defaults.
    """
    return {
        "max_open_positions": 10,
        "daily_loss_limit": round(initial_capital * 0.10, 2),
        "max_drawdown_pct": 25.0,
        "max_exposure": round(initial_capital * 5.0, 2),
    }


class BacktestRiskSimulator:
    """Per-run risk simulation over a BacktestBroker's simulated account.

    Pure synchronous reads of broker state — no Supabase, Redis, market
    status, broker connectivity or OMS involvement. One instance per run;
    instantiate with ``overrides=config.risk`` when ``risk_enabled``.
    """

    def __init__(self, initial_capital: float, overrides: dict | None = None):
        settings = _default_overrides(initial_capital)
        if overrides:
            settings.update({k: v for k, v in overrides.items() if v is not None})
        self._config = BacktestRiskConfig(**settings)
        self._initial_capital = float(initial_capital)
        self._peak_equity = self._initial_capital
        self._halted = False
        self._halt_rule = ""
        self._halt_reason = ""
        self._accepted = 0
        self._rejected: list[RiskRejection] = []
        self._rejection_counts: dict[str, int] = {}
        self._warnings: list[str] = []
        self._timeline: list[RiskTimelinePoint] = []

    # ── public surface ──

    @property
    def config(self) -> BacktestRiskConfig:
        return self._config

    @property
    def halted(self) -> bool:
        return self._halted

    @property
    def rejections(self) -> list[RiskRejection]:
        return list(self._rejected)

    @property
    def warnings(self) -> list[str]:
        return list(self._warnings)

    @property
    def acceptance_count(self) -> int:
        return self._accepted

    def check(self, broker, order) -> BacktestRiskCheck:
        """Evaluate one order against the simulated account state.

        Returns APPROVED (optionally with a clamped ``adjusted_quantity``
        from position sizing) or REJECTED with the rule + account state.
        """
        state = self._account_state(broker)

        symbol = getattr(order, "symbol", "")
        side = getattr(getattr(order, "side", None), "value", str(getattr(order, "side", "BUY")))
        quantity = abs(int(getattr(order, "quantity", 0) or 0))
        price = float(getattr(order, "price", 0) or 0)
        if price <= 0:
            price = broker.last_price(symbol)
        notional = quantity * price
        reducer = self._is_reducer(broker, symbol, side)

        # ── simulated kill switch / circuit breaker (halt state) ──
        if self._halted:
            return self._reject(order, state, RiskRuleType.CIRCUIT_BREAKER.value,
                                f"Trading halted by circuit breaker: {self._halt_reason}")
        if self._config.kill_switch_enabled:
            return self._reject(order, state, RiskRuleType.KILL_SWITCH.value,
                                "Kill switch is enabled for this simulation. All trading halted.")
        if self._config.emergency_stop:
            return self._reject(order, state, RiskRuleType.EMERGENCY_STOP.value,
                                "Emergency stop is enabled for this simulation. All trading halted.")

        # ── position sizing: clamp opening orders to the per-trade risk % ──
        if not reducer and self._config.max_risk_per_trade_pct > 0 and price > 0:
            max_notional = state["equity"] * self._config.max_risk_per_trade_pct / 100.0
            if notional > max_notional:
                clamped = max(int(max_notional // price), 1)
                if clamped < quantity:
                    self._accepted += 1
                    return BacktestRiskCheck(
                        decision=RiskDecision.APPROVED,
                        adjusted_quantity=clamped,
                        reason=(
                            f"Position sized from {quantity} to {clamped} "
                            f"(risk {self._config.max_risk_per_trade_pct:.1f}% of equity {state['equity']:.2f})."
                        ),
                    )

        # ── daily loss limit (hard limit → circuit breaker) ──
        if self._config.daily_loss_limit > 0 and state["pnl"] <= -self._config.daily_loss_limit:
            reason = f"Daily loss {state['pnl']:.2f} exceeds limit {self._config.daily_loss_limit:.2f}."
            self._halt(RiskRuleType.DAILY_LOSS_LIMIT.value, reason, state)
            return self._reject(order, state, RiskRuleType.DAILY_LOSS_LIMIT.value, reason)

        # ── daily profit target (warning, trade allowed) ──
        if self._config.daily_profit_target > 0 and state["pnl"] >= self._config.daily_profit_target:
            self._warnings.append(
                f"Daily profit {state['pnl']:.2f} has reached target {self._config.daily_profit_target:.2f}.",
            )

        # ── max trades per day ──
        if self._config.max_trades_per_day > 0 and state["trade_count"] >= self._config.max_trades_per_day:
            return self._reject(
                order, state, RiskRuleType.MAX_TRADES_PER_DAY.value,
                f"Trade count {state['trade_count']} exceeds daily limit {self._config.max_trades_per_day}.",
            )

        # ── capacity rules (reducers/close orders always pass) ──
        if not reducer:
            if self._config.max_open_positions > 0 and state["open_positions"] >= self._config.max_open_positions:
                return self._reject(
                    order, state, RiskRuleType.MAX_OPEN_POSITIONS.value,
                    f"Open positions {state['open_positions']} >= limit {self._config.max_open_positions}.",
                )
            if self._config.max_quantity > 0 and quantity > self._config.max_quantity:
                return self._reject(
                    order, state, RiskRuleType.MAX_QUANTITY.value,
                    f"Quantity {quantity} exceeds max {self._config.max_quantity}.",
                )
            if self._config.max_capital > 0 and state["capital_usage"] + notional > self._config.max_capital:
                return self._reject(
                    order, state, RiskRuleType.MAX_CAPITAL.value,
                    f"Capital usage {state['capital_usage'] + notional:.2f} exceeds limit {self._config.max_capital:.2f}.",
                )
            if self._config.max_exposure > 0 and state["exposure"] + notional > self._config.max_exposure:
                return self._reject(
                    order, state, RiskRuleType.MAX_EXPOSURE.value,
                    f"Exposure {state['exposure'] + notional:.2f} would exceed limit {self._config.max_exposure:.2f}.",
                )
            symbol_exposure = state["symbol_exposure"].get(symbol, 0.0)
            if self._config.max_symbol_exposure > 0 and symbol_exposure + notional > self._config.max_symbol_exposure:
                return self._reject(
                    order, state, RiskRuleType.MAX_SYMBOL_EXPOSURE.value,
                    f"Exposure in {symbol} {symbol_exposure + notional:.2f} exceeds limit {self._config.max_symbol_exposure:.2f}.",
                )

        # ── max drawdown (hard limit → circuit breaker) ──
        if self._config.max_drawdown_pct > 0 and state["drawdown_pct"] >= self._config.max_drawdown_pct:
            reason = f"Drawdown {state['drawdown_pct']:.1f}% exceeds limit {self._config.max_drawdown_pct:.1f}%."
            self._halt(RiskRuleType.MAX_DRAWDOWN.value, reason, state)
            return self._reject(order, state, RiskRuleType.MAX_DRAWDOWN.value, reason)

        self._accepted += 1
        return BacktestRiskCheck(decision=RiskDecision.APPROVED, details=state)

    def snapshot(self, broker, index: int, timestamp: str = "") -> None:
        """Record the per-candle risk state (risk timeline / curves)."""
        state = self._account_state(broker, timestamp=timestamp)
        self._timeline.append(
            RiskTimelinePoint(
                index=index,
                timestamp=timestamp,
                equity=round(state["equity"], 2),
                exposure=round(state["exposure"], 2),
                drawdown_pct=round(state["drawdown_pct"], 2),
                capital_remaining=round(state["capital_remaining"], 2),
                risk_remaining=round(state["risk_remaining"], 2),
                status="halted" if self._halted else "trading",
            ),
        )

    def analytics(self) -> RiskAnalytics:
        return RiskAnalytics(
            enabled=True,
            accepted_trades=self._accepted,
            rejected_trades=len(self._rejected),
            halt_count=1 if self._halted else 0,
            rejection_reasons=dict(self._rejection_counts),
            timeline=list(self._timeline),
            capital_curve=[
                RiskCurvePoint(index=p.index, timestamp=p.timestamp, value=p.capital_remaining)
                for p in self._timeline
            ],
            exposure_curve=[
                RiskCurvePoint(index=p.index, timestamp=p.timestamp, value=p.exposure)
                for p in self._timeline
            ],
            rejections=list(self._rejected),
        )

    # ── internal state derivation (broker is the only source of truth) ──

    def _account_state(self, broker, timestamp: str = "") -> dict:
        equity = float(broker.equity())
        self._peak_equity = max(self._peak_equity, equity)
        exposure = 0.0
        capital_usage = 0.0
        symbol_exposure: dict[str, float] = {}
        open_positions = 0
        for symbol, pos in broker.positions().items():
            qty = abs(float(pos.get("quantity", 0) or 0))
            avg = float(pos.get("avg_price", 0) or 0)
            notional = qty * avg
            exposure += notional
            capital_usage += notional
            symbol_exposure[symbol] = notional
            if qty > 0:
                open_positions += 1
        drawdown_pct = (
            (self._peak_equity - equity) / self._peak_equity * 100.0 if self._peak_equity > 0 else 0.0
        )
        pnl = equity - self._initial_capital
        if self._config.daily_loss_limit > 0:
            risk_remaining = max(self._config.daily_loss_limit + pnl, 0.0)
        else:
            risk_remaining = NO_LIMIT
        return {
            "equity": equity,
            "cash": float(broker.cash),
            "pnl": pnl,
            "trade_count": len(getattr(broker, "trades", []) or []),
            "exposure": exposure,
            "capital_usage": capital_usage,
            "symbol_exposure": symbol_exposure,
            "open_positions": open_positions,
            "drawdown_pct": max(drawdown_pct, 0.0),
            "capital_remaining": max(equity - exposure, 0.0),
            "risk_remaining": round(risk_remaining, 2),
            "timestamp": timestamp or self._timestamp(broker),
        }

    def _is_reducer(self, broker, symbol: str, side: str) -> bool:
        pos = broker.positions().get(symbol)
        if not pos:
            return False
        qty = float(pos.get("quantity", 0) or 0)
        if qty == 0:
            return False
        return (qty < 0 and side.upper() == "BUY") or (qty > 0 and side.upper() == "SELL")

    def _timestamp(self, broker) -> str:
        try:
            return broker.last_time()
        except Exception:
            return datetime.now(UTC).isoformat()

    def _halt(self, rule: str, reason: str, state: dict) -> None:
        if not self._config.circuit_breaker:
            return
        self._halted = True
        self._halt_rule = rule
        self._halt_reason = reason
        logger.info("Backtest risk circuit breaker engaged (%s): %s", rule, reason)

    def _reject(self, order, state: dict, rule: str, reason: str) -> BacktestRiskCheck:
        symbol = getattr(order, "symbol", "")
        side = getattr(getattr(order, "side", None), "value", str(getattr(order, "side", "BUY")))
        quantity = abs(int(getattr(order, "quantity", 0) or 0))
        price = float(getattr(order, "price", 0) or 0)
        record = RiskRejection(
            timestamp=state.get("timestamp") or "",
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=round(price, 4),
            rule=rule,
            reason=reason,
            capital_remaining=round(state.get("capital_remaining", 0.0), 2),
            risk_remaining=round(state.get("risk_remaining", NO_LIMIT), 2),
            drawdown=round(state.get("drawdown_pct", 0.0), 2),
            exposure=round(state.get("exposure", 0.0), 2),
        )
        self._rejected.append(record)
        self._rejection_counts[rule] = self._rejection_counts.get(rule, 0) + 1
        return BacktestRiskCheck(
            decision=RiskDecision.REJECTED, rule=rule, reason=reason, details=record.model_dump(),
        )
