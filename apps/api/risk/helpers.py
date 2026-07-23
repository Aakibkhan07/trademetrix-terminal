import logging
from datetime import datetime, timedelta, timezone

from core.db import get_supabase
from core.safe_query import async_safe_execute

logger = logging.getLogger(__name__)


async def compute_daily_pnl_fifo(user_id: str, broker: str | None = None) -> float:
    try:
        IST = timezone(timedelta(hours=5, minutes=30))
        today_start = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        supabase = get_supabase()
        query = (supabase.table("orders")
                 .select("symbol, side, quantity, filled_quantity, average_price, created_at")
                 .eq("user_id", user_id)
                 .eq("status", "FILLED")
                 .gte("created_at", today_start)
                 .order("created_at"))
        if broker:
            query = query.eq("broker", broker)
        filled = await async_safe_execute(query)
        if not filled:
            return 0.0

        sell_symbols = {o["symbol"] for o in filled if o["side"] == "SELL"}
        historical: dict[str, list[dict]] = {}
        for sym in sell_symbols:
            hist_rows = await async_safe_execute(
                supabase.table("orders")
                .select("quantity, filled_quantity, average_price")
                .eq("user_id", user_id)
                .eq("symbol", sym)
                .eq("side", "BUY")
                .eq("status", "FILLED")
                .lt("created_at", today_start)
                .order("created_at")
            )
            if hist_rows:
                historical[sym] = hist_rows

        pnl = 0.0
        buy_queue: dict[str, list[list[float]]] = {}

        for o in filled:
            sym = o["symbol"]
            qty = float(o.get("filled_quantity") if o.get("filled_quantity") is not None else o.get("quantity") or 0)
            price = float(o.get("average_price") or 0)
            if qty <= 0:
                continue

            if o["side"] == "BUY":
                buy_queue.setdefault(sym, []).append([qty, price])
            else:
                rem = qty
                queue = buy_queue.setdefault(sym, [])
                while rem > 0 and queue:
                    bqty, bprice = queue[0]
                    used = min(rem, bqty)
                    pnl += used * (price - bprice)
                    rem -= used
                    queue[0][0] -= used
                    if queue[0][0] <= 1e-8:
                        queue.pop(0)
                if rem > 0:
                    for h in historical.get(sym, []):
                        if rem <= 0:
                            break
                        hqty = float(h.get("filled_quantity") or h.get("quantity") or 0)
                        hprice = float(h.get("average_price") or 0)
                        if hqty > 0:
                            used = min(rem, hqty)
                            pnl += used * (price - hprice)
                            rem -= used
        return pnl
    except Exception as e:
        logger.warning("FIFO PnL computation failed for user=%s: %s", user_id, e)
        return 0.0


async def get_current_exposure(user_id: str) -> float:
    try:
        supabase = get_supabase()
        rows = await async_safe_execute(
            supabase.table("positions_snapshot")
            .select("quantity, average_buy_price").eq("user_id", user_id)
        )
        if not rows:
            return 0.0
        return sum(abs(r.get("quantity", 0)) * r.get("average_buy_price", 0) for r in rows)
    except Exception as e:
        logger.warning("Exposure calc failed for user=%s: %s", user_id, e)
        return 0.0


async def get_current_capital_usage(user_id: str) -> float:
    return await get_current_exposure(user_id)


async def get_open_position_count(user_id: str) -> int:
    try:
        supabase = get_supabase()
        rows = await async_safe_execute(
            supabase.table("positions_snapshot")
            .select("quantity").eq("user_id", user_id)
        )
        if not rows:
            return 0
        return len([r for r in rows if r.get("quantity", 0) != 0])
    except Exception as e:
        logger.warning("Open position count failed for user=%s: %s", user_id, e)
        return 0


async def get_drawdown(user_id: str) -> float:
    try:
        supabase = get_supabase()
        rows = await async_safe_execute(
            supabase.table("strategy_runs")
            .select("total_pnl").eq("user_id", user_id)
        )
        if not rows:
            return 0.0
        pnls = [float(r.get("total_pnl", 0)) for r in rows]
        peak = max(pnls) if pnls else 0
        current = sum(pnls)
        if peak <= 0:
            return 0.0
        return max(0.0, (peak - current) / peak * 100)
    except Exception as e:
        logger.warning("Drawdown calc failed for user=%s: %s", user_id, e)
        return 0.0


async def get_active_broker(user_id: str) -> str | None:
    try:
        supabase = get_supabase()
        rows = await async_safe_execute(
            supabase.table("broker_credentials")
            .select("broker")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .limit(1)
        )
        if rows:
            return rows[0]["broker"]
        return None
    except Exception as e:
        logger.warning("Active broker lookup failed for user=%s: %s", user_id, e)
        return None
