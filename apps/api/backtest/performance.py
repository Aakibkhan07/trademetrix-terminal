import logging
import math
from collections import defaultdict
from datetime import datetime
from typing import Any

from backtest.models import BacktestResult, EquityPoint, TradeRecord

logger = logging.getLogger(__name__)


def downsample_pairs(points: list[tuple], threshold: int = 2000) -> list[int]:
    """Return downsampled indices for a list of (x, y) pairs (shape-preserving)."""
    ys = [p[1] for p in points]
    n = len(points)
    if n <= threshold:
        return list(range(n))
    bucket_size = (n - 2) / (threshold - 2)
    chosen = [0]
    a = 0
    for i in range(threshold - 2):
        avg_range_start = int(math.floor((i + 1) * bucket_size) + 1)
        avg_range_end = int(math.floor((i + 2) * bucket_size) + 1)
        avg_range_end = min(avg_range_end, n)
        if avg_range_start >= avg_range_end:
            continue
        avg_x = (avg_range_start + avg_range_end - 1) / 2.0
        avg_y = sum(ys[j] for j in range(avg_range_start, avg_range_end)) / (avg_range_end - avg_range_start)
        range_offs = int(math.floor(i * bucket_size) + 1)
        range_to = int(math.floor((i + 1) * bucket_size) + 1)
        next_a = range_offs
        max_area = -1.0
        for j in range(range_offs, min(range_to, n - 1)):
            area = abs((ys[a] - avg_y) * (j - a) - (ys[a] - ys[j]) * (avg_x - a)) * 0.5
            if area > max_area:
                max_area = area
                next_a = j
        chosen.append(next_a)
        a = next_a
    chosen.append(n - 1)
    return sorted(set(chosen))


def compute_sharpe_ratio(returns: list[float]) -> float:
    """Canonical Sharpe ratio — the SINGLE definition used by every backtest path.

    Sample standard deviation (n - 1), annualized by sqrt(252). The legacy
    engine (engine/backtest.py) previously used population stdev over per-trade
    PnL, producing values that disagreed with this canonical path; both now
    share this function over equity-curve period returns.
    """
    if len(returns) < 2:
        return 0.0
    avg_r = sum(returns) / len(returns)
    variance = sum((r - avg_r) ** 2 for r in returns) / (len(returns) - 1)
    std_r = math.sqrt(variance) if variance > 0 else 0.0
    if std_r <= 0:
        return 0.0
    return round((avg_r / std_r) * math.sqrt(252), 2)


class PerformanceAnalytics:
    def calculate(
        self,
        result: BacktestResult,
        snapshots: list[dict],
        initial_capital: float,
        trades: list[TradeRecord],
        candles_analyzed: int,
        benchmark_candles: list[dict] | None = None,
        max_equity_points: int = 2000,
    ) -> BacktestResult:
        result.start_equity = initial_capital
        result.candles_analyzed = candles_analyzed

        self._compute_trade_stats(result, trades)
        self._compute_expectancy(result)
        self._compute_distributions(result)
        self._compute_equity_curve(result, snapshots, initial_capital)
        self._compute_drawdown(result)
        self._compute_ratios(result)
        self._compute_returns(result)
        if len(result.equity_curve) > max_equity_points:
            idx = downsample_pairs(
                [(i, p.equity) for i, p in enumerate(result.equity_curve)],
                threshold=max_equity_points,
            )
            result.equity_curve = [result.equity_curve[i] for i in idx]
        if benchmark_candles:
            self._compute_benchmark(result, benchmark_candles)

        if trades:
            avg_duration = sum(t.duration_minutes for t in trades) / len(trades)
            result.average_trade_duration_minutes = round(avg_duration, 1)

        return result

    def build_trades_from_snapshots(
        self,
        snapshots: list[dict],
        symbol: str,
    ) -> list[TradeRecord]:
        trades: list[TradeRecord] = []
        open_trade: dict[str, Any] | None = None

        for snap in snapshots:
            positions = snap.get("positions", [])
            pos = next((p for p in positions if p.get("symbol") == symbol), None)

            if not pos:
                if open_trade:
                    open_trade = None
                continue

            qty = pos.get("quantity", 0)
            if qty != 0 and not open_trade:
                is_short = qty < 0
                open_trade = {
                    "side": "SELL" if is_short else "BUY",
                    "entry_price": pos.get("average_sell_price", 0) if is_short else pos.get("average_buy_price", 0),
                    "quantity": abs(qty),
                    "entry_time": snap.get("timestamp", ""),
                }
            elif qty == 0 and open_trade:
                closed = TradeRecord(
                    symbol=symbol,
                    side=open_trade["side"],
                    entry_price=open_trade["entry_price"],
                    exit_price=pos.get("average_buy_price", 0) or pos.get("average_sell_price", 0) or pos.get("last_price", 0),
                    quantity=open_trade["quantity"],
                    pnl=0.0,
                    entry_time=open_trade["entry_time"],
                    exit_time=snap.get("timestamp", ""),
                )
                pnl = self._compute_pnl(
                    closed.side, closed.entry_price, closed.exit_price, closed.quantity,
                )
                closed.pnl = round(pnl, 2)
                trades.append(closed)
                open_trade = None

        return trades

    def _compute_trade_stats(self, result: BacktestResult, trades: list[TradeRecord]) -> None:
        result.total_trades = len(trades)
        if result.total_trades == 0:
            return

        result.trades = trades
        winning = [t for t in trades if t.pnl > 0]
        losing = [t for t in trades if t.pnl <= 0]

        result.winning_trades = len(winning)
        result.losing_trades = len(losing)
        result.win_rate = round(result.winning_trades / result.total_trades * 100, 2) if result.total_trades > 0 else 0.0

        result.gross_profit = round(sum(t.pnl for t in winning), 2)
        result.gross_loss = round(abs(sum(t.pnl for t in losing)), 2)
        result.net_pnl = round(result.gross_profit - result.gross_loss, 2)

        result.profit_factor = round(result.gross_profit / result.gross_loss, 2) if result.gross_loss > 0 else 0.0
        result.avg_win = round(result.gross_profit / result.winning_trades, 2) if result.winning_trades > 0 else 0.0
        result.avg_loss = round(result.gross_loss / result.losing_trades, 2) if result.losing_trades > 0 else 0.0
        result.largest_win = round(max((t.pnl for t in winning), default=0), 2)
        result.largest_loss = round(min((t.pnl for t in losing), default=0), 2)

        streak = 0
        max_win_streak = 0
        max_loss_streak = 0
        for t in trades:
            if t.pnl > 0:
                streak = streak + 1 if streak > 0 else 1
                max_win_streak = max(max_win_streak, streak)
            else:
                streak = streak - 1 if streak < 0 else -1
                max_loss_streak = max(max_loss_streak, abs(streak))

        result.max_consecutive_wins = max_win_streak
        result.max_consecutive_losses = max_loss_streak

    def _compute_expectancy(self, result: BacktestResult) -> None:
        """Expectancy per trade and reward:risk ratios (R = average loss)."""
        if result.total_trades == 0:
            return
        result.expectancy = round(result.net_pnl / result.total_trades, 2)
        if result.avg_loss > 0:
            result.expectancy_per_r = round(result.expectancy / result.avg_loss, 2)
            result.avg_risk_reward_ratio = round(result.avg_win / result.avg_loss, 2) if result.avg_win > 0 else 0.0
            abs_pnls = sorted(abs(t.pnl) for t in result.trades)
            n = len(abs_pnls)
            median = abs_pnls[n // 2] if n % 2 else (abs_pnls[n // 2 - 1] + abs_pnls[n // 2]) / 2
            result.median_risk_reward_ratio = round(median / result.avg_loss, 2)

    def _compute_distributions(self, result: BacktestResult) -> None:
        """Net PnL distribution by entry weekday, entry hour (IST), and month."""
        weekday: dict[str, float] = defaultdict(float)
        hour: dict[str, float] = defaultdict(float)
        month: dict[str, float] = defaultdict(float)
        days = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")

        for t in result.trades:
            try:
                ts = datetime.fromisoformat(str(t.entry_time).replace("Z", "+00:00"))
                weekday[days[ts.weekday()]] += t.pnl
                hour[ts.strftime("%H")] += t.pnl
                month[ts.strftime("%Y-%m")] += t.pnl
            except (ValueError, AttributeError, KeyError):
                continue

        result.weekday_distribution = {k: round(v, 2) for k, v in sorted(weekday.items())}
        result.hour_distribution = {k: round(v, 2) for k, v in sorted(hour.items())}
        result.month_distribution = {k: round(v, 2) for k, v in sorted(month.items())}

    def _compute_benchmark(self, result: BacktestResult, benchmark_candles: list[dict]) -> None:
        """Buy-and-hold benchmark from the candle series: return, max DD, beta, alpha."""
        closes = [float(c.get("close", 0)) for c in benchmark_candles if float(c.get("close", 0)) > 0]
        if len(closes) < 2:
            return

        bench_return_pct = (closes[-1] - closes[0]) / closes[0] * 100
        result.benchmark_return_pct = round(bench_return_pct, 2)
        result.excess_return_pct = round(result.return_pct - bench_return_pct, 2)

        peak = closes[0]
        max_dd = 0.0
        for c in closes:
            peak = max(peak, c)
            dd = (peak - c) / peak * 100 if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        result.benchmark_max_drawdown_pct = round(max_dd, 2)

        strategy_returns = self._get_period_returns(result.equity_curve)
        if len(strategy_returns) < 2:
            return
        bench_returns = [
            (closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(1, len(closes)) if closes[i - 1] > 0
        ]
        n = min(len(strategy_returns), len(bench_returns))
        if n < 2:
            return
        sr = strategy_returns[-n:]
        br = bench_returns[-n:]

        mean_s = sum(sr) / n
        mean_b = sum(br) / n
        var_b = sum((r - mean_b) ** 2 for r in br) / (n - 1) if n > 1 else 0.0
        cov = sum((a - mean_s) * (b - mean_b) for a, b in zip(sr, br)) / (n - 1) if n > 1 else 0.0
        if var_b > 0:
            result.beta = round(cov / var_b, 2)
        annualized_s = mean_s * 252 * 100
        annualized_b = mean_b * 252 * 100
        result.alpha = round(annualized_s - result.beta * annualized_b, 2) if result.beta else 0.0

    def _compute_equity_curve(
        self,
        result: BacktestResult,
        snapshots: list[dict],
        initial_capital: float,
    ) -> None:
        equity_curve = []
        for snap in snapshots:
            equity = snap.get("equity", initial_capital)
            ts = snap.get("timestamp", "")
            equity_curve.append(EquityPoint(timestamp=ts, equity=round(equity, 2)))

        result.equity_curve = equity_curve
        if equity_curve:
            result.end_equity = equity_curve[-1].equity
        else:
            result.end_equity = initial_capital

        result.return_pct = round(
            (result.end_equity - initial_capital) / initial_capital * 100, 2,
        ) if initial_capital > 0 else 0.0

    def _compute_drawdown(self, result: BacktestResult) -> None:
        if not result.equity_curve:
            return

        peak = result.start_equity
        max_dd = 0.0
        max_dd_pct = 0.0

        for point in result.equity_curve:
            eq = point.equity
            if eq > peak:
                peak = eq
            dd = peak - eq
            dd_pct = dd / peak * 100 if peak > 0 else 0.0
            point.drawdown = round(dd, 2)
            point.drawdown_pct = round(dd_pct, 2)

            if dd > max_dd:
                max_dd = dd
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

        result.max_drawdown = round(max_dd, 2)
        result.max_drawdown_pct = round(max_dd_pct, 2)

    def _compute_ratios(self, result: BacktestResult) -> None:
        returns = self._get_period_returns(result.equity_curve)
        if len(returns) < 2:
            return

        result.sharpe_ratio = compute_sharpe_ratio(returns)
        avg_r = sum(returns) / len(returns)

        neg_returns = [r for r in returns if r < 0]
        if neg_returns:
            avg_neg = sum(neg_returns) / len(neg_returns)
            neg_var = sum((r - avg_neg) ** 2 for r in neg_returns) / len(neg_returns)
            downside_std = math.sqrt(neg_var) if neg_var > 0 else 0.0
            if downside_std > 0:
                result.sortino_ratio = round((avg_r / downside_std) * math.sqrt(252), 2)

        if result.max_drawdown_pct > 0:
            annualized_return = avg_r * 252 if returns else 0
            result.calmar_ratio = round(annualized_return / result.max_drawdown_pct * 100, 2) if result.max_drawdown_pct > 0 else 0.0

    def _compute_returns(self, result: BacktestResult) -> None:
        monthly: dict[str, list[float]] = defaultdict(list)
        daily: dict[str, list[float]] = defaultdict(list)

        prev_equity = result.start_equity
        for point in result.equity_curve:
            eq = point.equity
            ret = (eq - prev_equity) / prev_equity if prev_equity > 0 else 0.0

            try:
                ts = datetime.fromisoformat(point.timestamp.replace("Z", "+00:00"))
                month_key = ts.strftime("%Y-%m")
                day_key = ts.strftime("%Y-%m-%d")
                monthly[month_key].append(ret)
                daily[day_key].append(ret)
            except (ValueError, AttributeError):
                pass

            prev_equity = eq

        result.monthly_returns = {
            k: round(sum(v) * 100, 2) for k, v in monthly.items()
        }
        result.daily_returns = {
            k: round(sum(v) * 100, 2) for k, v in daily.items()
        }

    def _get_period_returns(self, equity_curve: list[EquityPoint]) -> list[float]:
        if len(equity_curve) < 2:
            return []
        returns = []
        for i in range(1, len(equity_curve)):
            prev = equity_curve[i - 1].equity
            curr = equity_curve[i].equity
            if prev > 0:
                returns.append((curr - prev) / prev)
        return returns

    def _compute_pnl(self, side: str, entry: float, exit: float, qty: int) -> float:
        if side == "BUY":
            return (exit - entry) * qty
        else:
            return (entry - exit) * qty


performance_analytics = PerformanceAnalytics()
