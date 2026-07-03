import logging
from typing import Optional

from core.config import settings
from core.db import get_supabase

logger = logging.getLogger(__name__)

_WHITELISTED_ACTIONS = {
    "query_positions", "query_funds", "query_orderbook",
    "square_off", "pause_strategy", "resume_strategy",
    "query_pnl", "query_risk_status", "query_strategies",
}


class AIDesk:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self._client: Optional = None

    def _get_client(self):
        if self._client is None and settings.gemini_api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=settings.gemini_api_key)
            except ImportError:
                logger.warning("google-genai not installed; AI desk unavailable")
        return self._client

    async def process_command(self, command: str) -> dict:
        client = self._get_client()
        if not client:
            return {"response": "AI desk is not available. Check GEMINI_API_KEY configuration.", "action": None}

        context = await self._build_context()

        prompt = f"""You are the AI Trading Desk for Trade Metrix Terminal.

User context:
{context}

User command: {command}

Interpret the command and return JSON with:
1. "action" — one of: {', '.join(sorted(_WHITELISTED_ACTIONS))}, or "unknown" if the command is not in the whitelist, or "query_general" for informational queries
2. "params" — any parameters needed (symbol, quantity, etc.)
3. "response" — a natural language response to the user
4. "needs_confirmation" — true if the action is destructive (square_off, pause_strategy)

CRITICAL: Never execute destructive actions without user confirmation. Never bypass risk controls.
Never give financial advice or recommendations. You are a tool, not a SEBI-registered advisor.
"""

        try:
            result = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            text = result.text.strip()
            import json
            parsed = json.loads(text.replace("```json", "").replace("```", "").strip())
            return parsed
        except Exception as e:
            logger.error(f"AI desk error: {e}", exc_info=True)
            return {"response": "I encountered an error processing your request.", "action": None}

    async def _build_context(self) -> str:
        supabase = get_supabase()
        parts = []

        try:
            funds = supabase.table("positions_snapshot").select("*").eq("user_id", self.user_id).execute()
            parts.append(f"Open positions: {len(funds.data or [])}")
        except Exception as e:
            logger.warning("Failed to fetch AI desk context for user %s: %s", self.user_id, e)

        try:
            result = supabase.table("risk_settings").select("*").eq("user_id", self.user_id).single().execute()
            if result.data:
                rs = result.data
                parts.append(f"Risk: kill_switch={'ON' if rs.get('kill_switch_enabled') else 'OFF'}, mode={'LIVE' if rs.get('is_live') else 'PAPER'}, max_daily_loss={rs.get('max_daily_loss', 0)}")
        except Exception as e:
            logger.warning("Failed to fetch AI desk context for user %s: %s", self.user_id, e)

        try:
            strat = supabase.table("strategies").select("name, is_active").eq("user_id", self.user_id).execute()
            names = [s["name"] for s in (strat.data or []) if s.get("is_active")]
            parts.append(f"Active strategies: {', '.join(names) if names else 'none'}")
        except Exception as e:
            logger.warning("Failed to fetch AI desk context for user %s: %s", self.user_id, e)

        return "\n".join(parts)
