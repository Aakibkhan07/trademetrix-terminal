"""Strategy Execution Context — read-only snapshot for manual evaluation and
status views.

Exposes: current position, portfolio, PnL, open orders, risk limits, market
data, historical data, indicators, time/session, broker/account health and
strategy variables. All reads are best-effort and fail-open (a queryable
component that errors degrades the field, never the runtime).

The runtime worker additionally injects the position subset (quantity/avg/PnL)
into ``GraphStrategy._memory`` before each candle evaluation so the builder's
``source.position`` block reports the execution engine's real position state.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta, timezone

from core.models import Candle, Tick
from strategy_runtime.models import StrategySpec

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


def _session(now: datetime = None) -> str:
    now = now or datetime.now(IST)
    current = now.hour * 60 + now.minute
    if current < 555:
        return "PRE_MARKET"
    if current < 915:
        return "OPENING"
    if current < 930:
        return "EARLY"
    if current < 1500:
        return "REGULAR"
    if current < 1530:
        return "CLOSING"
    if current < 1555:
        return "POST_CLOSE"
    return "CLOSED"


def _indicators(closes: list[float]) -> dict:
    from strategies.indicators import ema, sma

    out: dict = {}
    if not closes:
        return out
    for period in (5, 10, 20, 50):
        if len(closes) >= period:
            out[f"sma_{period}"] = round(sma(closes, period), 4)
            out[f"ema_{period}"] = round(ema(closes, period), 4)
    if len(closes) >= 15:
        try:
            gains, losses = 0.0, 0.0
            for i in range(-14, 0):
                change = closes[i] - closes[i - 1]
                if change >= 0:
                    gains += change
                else:
                    losses -= change
            if losses == 0:
                rsi = 100.0
            else:
                rsi = 100.0 - (100.0 / (1.0 + gains / losses))
            out["rsi_14"] = round(rsi, 4)
        except Exception:
            pass
    return out


async def build_execution_context(
    spec: StrategySpec,
    *,
    tick: Tick | None = None,
    candle: Candle | None = None,
    candles: dict[str, list[Candle]] | None = None,
    last_price: float = 0.0,
) -> dict:
    """Full read-only execution context (manual evaluate / status views)."""
    now = datetime.now(UTC)
    ctx: dict = {
        "strategy": {
            "strategy_id": spec.strategy_id,
            "symbol": spec.symbol,
            "exchange": spec.exchange,
            "interval": spec.interval,
            "timeframes": list(spec.timeframes),
            "mode": spec.mode,
            "trigger": spec.trigger.value,
            "quantity": spec.quantity,
            "variables": dict(spec.variables),
        },
        "time": {"utc": now.isoformat(), "ist": now.astimezone(IST).isoformat(), "timestamp": now.isoformat()},
        "market": {"open": _market_open(), "session": _session()},
        "tick": _tick_dict(tick, spec.symbol, last_price=last_price),
        "candle": _candle_dict(candle),
        "candles": _candles_dict(candles or {}),
        "indicators": {},
        "position": _position_context(spec),
        "portfolio": _portfolio_context(spec),
        "open_orders": [],
        "risk": {
            "is_paper": spec.is_paper,
            "max_positions": spec.max_positions,
            "max_risk_per_trade": spec.max_risk_per_trade,
            "max_daily_trades": spec.max_daily_trades,
            "quantity": spec.quantity,
        },
        "historical": {},
        "broker": _broker_context(spec),
        "variables": dict(spec.variables),
    }
    if candles and spec.interval in candles:
        closes = [c.close for c in candles[spec.interval]]
        ctx["indicators"] = _indicators(closes)
        ctx["candles"] = _candles_dict(candles)
    ctx["open_orders"] = await _open_orders(spec)
    ctx["historical"] = await _historical(spec)
    return ctx


def _market_open() -> bool:
    try:
        from market.status import market_status_service

        return market_status_service.is_market_open()
    except Exception:
        return False


def _candle_dict(candle: Candle | None) -> dict | None:
    if candle is None:
        return None
    return {
        "symbol": candle.symbol,
        "exchange": candle.exchange.value if hasattr(candle.exchange, "value") else str(candle.exchange),
        "interval": candle.interval,
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
        "timestamp": candle.timestamp.isoformat() if isinstance(candle.timestamp, datetime) else candle.timestamp,
        "oi": candle.oi,
    }


def _candles_dict(candles: dict[str, list[Candle]]) -> dict[str, list[dict]]:
    return {tf: [c for c in (_candle_dict(c) for c in series) if c] for tf, series in candles.items()}


def _tick_dict(tick: Tick | None, symbol: str, last_price: float) -> dict:
    if tick:
        return {
            "symbol": tick.symbol,
            "last_price": tick.last_price,
            "bid": tick.bid,
            "ask": tick.ask,
            "volume": tick.volume,
            "oi": tick.oi,
        }
    if last_price:
        return {"symbol": symbol, "last_price": last_price, "bid": 0, "ask": 0, "volume": 0, "oi": 0}
    try:
        from market.cache import market_cache

        q = market_cache.get_quote(symbol) or {}
        return {
            "symbol": symbol,
            "last_price": q.get("last_price", 0),
            "bid": q.get("bid", 0),
            "ask": q.get("ask", 0),
            "volume": q.get("volume", 0),
            "oi": q.get("oi", 0),
        }
    except Exception:
        return {"symbol": symbol, "last_price": 0, "bid": 0, "ask": 0, "volume": 0, "oi": 0}


def _position_context(spec: StrategySpec) -> dict:
    try:
        from execution_engine import position_manager

        broker = spec.broker or "paper"
        pos = position_manager.get_position(spec.user_id, broker, spec.symbol)
        if pos is None:
            return {"symbol": spec.symbol, "broker": broker, "quantity": 0, "average_price": 0.0, "pnl": 0.0}
        return {
            "symbol": pos.symbol,
            "broker": pos.broker,
            "quantity": pos.quantity,
            "average_price": pos.average_price,
            "last_price": pos.last_price,
            "realised_pnl": pos.realised_pnl,
            "unrealised_pnl": pos.unrealised_pnl,
            "pnl": float(getattr(pos, "realised_pnl", 0) + getattr(pos, "unrealised_pnl", 0)),
        }
    except Exception as e:
        logger.debug("position context skipped: %s", e)
        return {"symbol": spec.symbol, "quantity": 0, "average_price": 0.0, "pnl": 0.0}


def _portfolio_context(spec: StrategySpec) -> dict:
    broker = spec.broker or "paper"
    try:
        from execution_engine import pnl_engine, portfolio_engine

        snapshot = portfolio_engine.snapshot(spec.user_id)
        account = pnl_engine.get_account(spec.user_id, broker)
        return {
            "user_id": spec.user_id,
            "open_positions": snapshot.open_positions if snapshot else 0,
            "realised_pnl": snapshot.realised_pnl if snapshot else (account.realised_pnl if account else 0.0),
            "unrealised_pnl": snapshot.unrealised_pnl if snapshot else (account.unrealised_pnl if account else 0.0),
            "daily_pnl": snapshot.daily_pnl if snapshot else (account.daily_pnl if account else 0.0),
            "equity": snapshot.current_equity if snapshot else (account.current_equity if account else 0.0),
            "drawdown_pct": snapshot.drawdown_pct if snapshot else 0.0,
            "broker": broker,
        }
    except Exception as e:
        logger.debug("portfolio context skipped: %s", e)
        return {"user_id": spec.user_id, "equity": 0.0, "open_positions": 0, "broker": broker}


async def _open_orders(spec: StrategySpec) -> list[dict]:
    try:
        from oms.manager import order_manager

        orders = await order_manager.get_active_orders(spec.user_id)
        return [
            {
                "order_id": o.order_id,
                "symbol": o.symbol,
                "side": o.side,
                "quantity": o.quantity,
                "price": o.price,
                "status": o.state,
                "broker_order_id": getattr(o, "broker_order_id", ""),
            }
            for o in orders
        ]
    except Exception as e:
        logger.debug("open orders context skipped: %s", e)
        return []


async def _historical(spec: StrategySpec) -> dict:
    try:
        from market.historical import historical_engine

        candles = await historical_engine.get_historical(
            symbol=spec.symbol,
            interval=spec.interval,
            days=2,
            user_id=spec.user_id,
        )
        return {"symbol": spec.symbol, "interval": spec.interval, "candles": candles or []}
    except Exception as e:
        logger.debug("historical context skipped: %s", e)
        return {"symbol": spec.symbol, "interval": spec.interval, "candles": []}


def _broker_context(spec: StrategySpec) -> dict:
    try:
        from brokers.sdk.health import broker_health_service

        state = broker_health_service.state(spec.broker or "paper")
        return {
            "broker": spec.broker or "paper",
            "account": spec.account,
            "connected": state in ("connected", "websocket_healthy", "rest_healthy"),
            "state": state,
        }
    except Exception:
        return {"broker": spec.broker or "paper", "account": spec.account, "connected": None, "state": "unknown"}


def position_memory_for(strategy, spec: StrategySpec) -> None:
    """Inject the execution engine's position state so the builder
    ``source.position`` block reports reality (additive; no engine changes)."""
    try:
        from execution_engine import position_manager

        positions = position_manager.get_positions(spec.user_id) or []
        broker = spec.broker or "paper"
        pos = next((p for p in positions if (p.broker or "paper") == broker and p.symbol == spec.symbol), None)
        try:
            memory = strategy._memory
        except AttributeError:
            memory = None
        if memory is None:
            return
        if pos is None:
            memory["position_qty"] = 0
            memory["position_avg"] = 0
            memory["position_pnl"] = 0
            return
        memory["position_qty"] = pos.quantity
        memory["position_avg"] = pos.average_price
        memory["position_pnl"] = float(
            getattr(pos, "realised_pnl", 0) + getattr(pos, "unrealised_pnl", 0)
        )
    except Exception as e:
        logger.debug("position_memory injection skipped: %s", e)
