import json
import logging
from datetime import UTC, datetime, timedelta

from core.db import async_supabase, get_supabase

from .openrouter import chat_completion

logger = logging.getLogger(__name__)


class AIJournal:
    def __init__(self, user_id: str):
        self.user_id = user_id

    async def analyze_trades(self, lookback_days: int = 7) -> dict:
        trades_data = await self._get_recent_trades(lookback_days)
        if not trades_data:
            return {"analysis": "No trades found in the selected period.", "stats": {}}

        stats = self._compute_stats(trades_data, lookback_days)

        prompt = f"""You are the AI Trade Journal for Trade Metrix Terminal.
You provide psychological and statistical feedback on trading behaviour.

Recent trading data (last {lookback_days} days):
{json.dumps(trades_data, indent=2)}

Aggregated stats:
{json.dumps(stats, indent=2)}

Analyze this trader's behaviour. Return JSON with:
1. "summary" — 2-3 sentence overview of their trading
2. "strengths" — what they are doing well
3. "weaknesses" — patterns to improve (overtrading, revenge trading, ignoring stops)
4. "score" — a discipline score 1-100
5. "tip" — one actionable tip for improvement

Important guidelines:
- Be constructive, never shaming
- Focus on behavioural patterns, not just P&L
- Quantify the cost of undisciplined behaviour if evident
- Do NOT give financial or investment advice
- You are a journal tool, not a SEBI-registered advisor
"""

        text = await chat_completion(prompt)
        if text is None:
            return {"analysis": "AI journal not available. Configure OPENROUTER_API_KEY.", "stats": stats}
        try:
            analysis = json.loads(text.replace("```json", "").replace("```", "").strip())
            await self._save_entry(analysis, trades_data)
            return {"analysis": analysis, "stats": stats}
        except Exception as e:
            logger.error(f"AI journal error: {e}", exc_info=True)
            return {"analysis": "Could not generate analysis.", "stats": stats}

    async def _get_recent_trades(self, lookback_days: int) -> list:
        """Return the user's recent filled trades.

        The `orders` table is the canonical fill ledger (it carries the full
        order schema incl. a `created_at` column on prod). The legacy `trades`
        table is queried as a fallback when no filled orders exist; if that
        table's schema drifts (missing columns), the query degrades gracefully
        to an empty list so the journal never 500s.
        """
        since = (datetime.now(UTC) - timedelta(days=lookback_days)).isoformat()
        supabase = get_supabase()

        try:
            orders = await async_supabase(lambda: supabase.table("orders").select("*").eq("user_id", self.user_id).gte(
                "created_at", since
            ).eq("status", "FILLED").order("created_at", desc=True).limit(100).execute())
            if orders.data:
                return [
                    {
                        "id": o.get("id"),
                        "symbol": o.get("symbol", ""),
                        "side": o.get("side", ""),
                        "quantity": o.get("filled_quantity", o.get("quantity", 0)),
                        "price": o.get("average_price", o.get("price", 0)),
                        "value": o.get("total_value", 0) or 0,
                        "created_at": o.get("created_at"),
                        "is_paper": o.get("is_paper", True),
                        "source": "orders",
                    }
                    for o in orders.data
                ]
        except Exception as e:
            logger.warning("AI journal: orders query failed, falling back to trades: %s", e)

        try:
            result = await async_supabase(lambda: supabase.table("trades").select("*").eq("user_id", self.user_id).gte(
                "created_at", since
            ).limit(100).execute())
            if result.data:
                return result.data
        except Exception as e:
            logger.warning("AI journal: trades query failed (schema drift likely): %s", e)
        return []

    def _compute_stats(self, trades: list, lookback_days: int = 7) -> dict:
        total = len(trades)
        if total == 0:
            return {}

        buys = sum(1 for t in trades if t.get("side") == "BUY")
        sells = total - buys
        total_value = sum(float(t.get("value", 0)) for t in trades)
        unique_symbols = len(set(t.get("symbol", "") for t in trades))

        return {
            "total_trades": total,
            "buy_trades": buys,
            "sell_trades": sells,
            "total_value": round(total_value, 2),
            "unique_symbols": unique_symbols,
            "period_days": lookback_days,
        }

    async def _save_entry(self, analysis: dict, trades: list) -> None:
        supabase = get_supabase()
        trade_ids = [t.get("id") for t in trades if t.get("id")]
        entry = {
            "user_id": self.user_id,
            "entry_type": "ai_analysis",
            "content": json.dumps(analysis),
            "tags": ["ai_analysis", "journal"],
            "trade_ids": trade_ids,
        }
        try:
            await async_supabase(lambda: supabase.table("journal_entries").insert(entry).execute())
        except Exception as e:
            logger.warning("Failed to save journal entry: %s", e)
