"""Reproduce the three reported backtest defects, with the arithmetic visible.

Read-only with respect to the repo: no broker, no OMS, no network. The price series is a
deterministic synthetic oscillation so both signal directions occur repeatedly and the numbers
reproduce on any machine.

    python scripts/repro_backtest_defects.py

For each strategy this prints, per emitted order, the notional it implies against the starting
capital, then the broker's final cash / equity / realized P&L, and whether the recorded trades
reconcile with the equity change.
"""

import asyncio
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.execution import BacktestBroker, BacktestExecutionConfig  # noqa: E402
from backtest.risk import BacktestRiskSimulator  # noqa: E402
from core.constants import LOT_SIZES  # noqa: E402
from core.models import Candle  # noqa: E402
from strategies import get_strategy  # noqa: E402

CAPITAL = 1_000_000.0
SYMBOL = "NSE:NIFTY50-INDEX"
BARE = "NIFTY50-INDEX"


def synth(n: int = 400, start: float = 24000.0, amplitude: float = 0.06) -> list[dict]:
    """Two interleaved cycles, so the series crosses over in both directions repeatedly."""
    out = []
    for i in range(n):
        price = start * (1 + amplitude * math.sin(i / 9.0) + 0.4 * amplitude * math.sin(i / 3.0))
        out.append(
            {
                "symbol": SYMBOL,
                "timestamp": f"2026-01-{1 + (i % 28):02d}T00:00:00+05:30",
                "open": price,
                "high": price * 1.004,
                "low": price * 0.996,
                "close": price,
                "volume": 1000,
            }
        )
    return out


def to_candle(raw: dict) -> Candle:
    return Candle(
        symbol=SYMBOL,
        exchange="NSE",
        interval="1d",
        timestamp=raw["timestamp"],
        open=raw["open"],
        high=raw["high"],
        low=raw["low"],
        close=raw["close"],
        volume=raw["volume"],
    )


async def trace(key: str, candles: list[dict]) -> dict:
    print(f"\n{'=' * 76}\n  {key}\n{'=' * 76}")

    broker = BacktestBroker("bt:repro")
    broker.update_config(BacktestExecutionConfig(initial_capital=CAPITAL, seed=1))
    await broker.connect()
    broker.set_candles(candles)

    strategy = get_strategy(key)({"symbol": SYMBOL})
    await strategy.on_start()

    risk = BacktestRiskSimulator(initial_capital=CAPITAL, overrides={})
    emitted = 0
    blocked: list[str] = []
    worst_notional_ratio = 0.0
    for idx, raw in enumerate(candles):
        await broker.on_candle(idx)
        sig = await strategy.on_candle(to_candle(raw))
        if not sig or not getattr(sig, "orders", None):
            continue
        for order in sig.orders:
            emitted += 1
            px = raw["close"]
            notional = order.quantity * px
            ratio = notional / CAPITAL
            worst_notional_ratio = max(worst_notional_ratio, ratio)
            if emitted <= 3:
                print(f"\n  order #{emitted}: {order.side.value} qty={order.quantity} @ ~{px:,.1f}")
                print(f"    notional            = {order.quantity} x {px:,.1f} = {notional:,.0f}")
                print(f"    capital             = {CAPITAL:,.0f}")
                print(f"    notional / capital  = {ratio:.2f}x")

            # Mirror manager._place_via_broker: risk engine first, then the broker.
            if risk is not None:
                check = risk.check(broker, order)
                if str(check.decision).endswith("REJECTED"):
                    blocked.append(f"{check.rule}: {check.reason}")
                    continue
                if check.adjusted_quantity is not None and emitted <= 3:
                    print(f"    risk ADJUSTED qty  : {order.quantity} -> {check.adjusted_quantity}")
            await broker.place_order(order)
    await strategy.on_stop()

    # Close whatever is left, the way the manager does at the end of a run.
    for sym, pos in list(broker.positions().items()):
        if pos["quantity"] != 0:
            last = candles[-1]["close"]
            side = "SELL" if pos["quantity"] > 0 else "BUY"
            from core.models import Exchange, OrderSide, OrderType, ProductType

            from execution.models import NormalizedOrder

            await broker.place_order(
                NormalizedOrder(
                    symbol=sym,
                    exchange=Exchange.NSE,
                    side=OrderSide.SELL if side == "SELL" else OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    product=ProductType.INTRADAY,
                    quantity=abs(pos["quantity"]),
                    price=last,
                )
            )

    equity = broker.equity()
    trades = broker.trades
    trade_pnl = sum(t["pnl"] for t in trades)

    print(f"\n  orders emitted            : {emitted}")
    print(f"  worst notional / capital  : {worst_notional_ratio:.2f}x")
    print(f"  broker cash               : {broker.cash:,.2f}")
    print(f"  broker realized pnl       : {broker.realized_pnl:,.2f}")
    print(f"  broker equity             : {equity:,.2f}")
    print(f"  equity change             : {equity - CAPITAL:,.2f}")
    print(f"  trades recorded           : {len(trades)}")
    print(f"  sum(trade pnl)            : {trade_pnl:,.2f}")
    missing_ts = sum(1 for t in trades if not t.get("entry_time") or not t.get("exit_time"))
    print(f"  trades missing timestamps : {missing_ts}/{len(trades)}")
    if blocked:
        from collections import Counter

        print(f"  risk-blocked orders       : {len(blocked)}")
        for reason, n in Counter(blocked).most_common(3):
            print(f"      {n:>4}  {reason[:88]}")
    print(f"  equity below zero         : {equity < 0}")
    costs = broker.total_costs
    print(f"  broker total costs    : {costs:,.2f}")
    # Project's accounting contract: trade P&L is GROSS, costs are separate, and they
    # reconcile as gross - costs == equity change. Checking gross alone is expected to miss by
    # exactly the costs, so state both.
    gross_only = abs(trade_pnl - (equity - CAPITAL)) < 1.0
    fee_aware = abs(trade_pnl - costs - (equity - CAPITAL)) < 1.0
    print(f"  gross == eq-start           : {gross_only}")
    print(f"  gross - costs == eq-start   : {fee_aware}   (project contract)")

    return {
        "emitted": emitted,
        "worst_ratio": worst_notional_ratio,
        "equity": equity,
        "trade_pnl": trade_pnl,
        "trades": len(trades),
        "missing_ts": missing_ts,
        "reconciles": fee_aware,
        "gross_only": gross_only,
        "costs": costs,
        "negative": equity < 0,
    }


async def main() -> None:
    print(f"  capital                 : {CAPITAL:,.0f}")
    print(f"  symbol                  : {SYMBOL}")
    print(f"  LOT_SIZES['{SYMBOL}']    : {LOT_SIZES.get(SYMBOL, 'ABSENT -> falls back to 75')}")
    print(f"  LOT_SIZES['{BARE}']      : {LOT_SIZES.get(BARE, 'ABSENT')}")
    candles = synth()
    closes = [c["close"] for c in candles]
    print(f"  synthetic candles       : {len(candles)}  range {min(closes):,.0f} .. {max(closes):,.0f}")

    for key in ("trend_rider", "macd_cross"):
        await trace(key, candles)


if __name__ == "__main__":
    asyncio.run(main())
