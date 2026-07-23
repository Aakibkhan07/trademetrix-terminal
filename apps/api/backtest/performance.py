import logging
import math
from collections import defaultdict
from datetime import datetime
from typing import Any

from backtest.models import BacktestResult, EquityPoint, TradeRecord

logger = logging.getLogger(__name__)


class PerformanceAnalytics:
    def calculate(
        self,
        result: BacktestResult,
        snapshots: list[dict],
        initial_capital: float,
        trades: list[TradeRecord],
        candles_analyzed: int,
    ) -> BacktestResult:
        result.start_equity = initial_capital
        result.candles_analyzed = candles_analyzed

        self._compute_trade_stats(result, trades)
        self._compute_equity_curve(result, snapshots, initial_capital)
        self._compute_drawdown(result)
        self._compute_ratios(result)
        self._compute_returns(result)

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
                open_trade = {
                    "side": "BUY" if qty > 0 else "SELL",
                    "entry_price": pos.get("average_buy_price", 0),
                    "quantity": abs(qty),
                    "entry_time": snap.get("timestamp", ""),
                }
            elif qty == 0 and open_trade:
                closed = TradeRecord(
                    symbol=symbol,
                    side=open_trade["side"],
                    entry_price=open_trade["entry_price"],
                    exit_price=pos.get("average_sell_price", 0) or pos.get("last_price", 0),
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

        avg_r = sum(returns) / len(returns)
        variance = sum((r - avg_r) ** 2 for r in returns) / (len(returns) - 1)
        std_r = math.sqrt(variance) if variance > 0 else 0.0

        if std_r > 0:
            result.sharpe_ratio = round((avg_r / std_r) * math.sqrt(252), 2)

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
