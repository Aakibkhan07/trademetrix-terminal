import json
import logging
from datetime import datetime
from typing import Optional

from core.config import settings
from core.db import get_supabase

logger = logging.getLogger(__name__)


class AIJournal:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self._client: Optional = None

    def _get_client(self):
        if self._client is None and settings.gemini_api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=settings.gemini_api_key)
            except ImportError:
                pass
        return self._client

    async def analyze_trades(self, lookback_days: int = 7) -> dict:
        client = self._get_client()
        if not client:
            return {"analysis": "AI journal not available. Configure GEMINI_API_KEY."}

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

        try:
            result = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            text = result.text.strip()
            analysis = json.loads(text.replace("```json", "").replace("```", "").strip())
            await self._save_entry(analysis, trades_data)
            return {"analysis": analysis, "stats": stats}
        except Exception as e:
            logger.error(f"AI journal error: {e}", exc_info=True)
            return {"analysis": "Could not generate analysis.", "stats": stats}

    async def _get_recent_trades(self, lookback_days: int) -> list:
        supabase = get_supabase()
        result = supabase.table("trades").select("*").eq("user_id", self.user_id).gte(
            "created_at", datetime.utcnow().isoformat()
        ).limit(100).execute()
        return result.data or []

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
            supabase.table("journal_entries").insert(entry).execute()
        except Exception as e:
            logger.warning("Failed to save journal entry: %s", e)
