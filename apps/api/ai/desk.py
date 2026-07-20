import json
import logging

from core.db import get_supabase

from .openrouter import chat_completion

logger = logging.getLogger(__name__)

_WHITELISTED_ACTIONS = {
    "query_positions", "query_funds", "query_orderbook",
    "square_off", "pause_strategy", "resume_strategy",
    "query_pnl", "query_risk_status", "query_strategies",
}


class AIDesk:
    def __init__(self, user_id: str):
        self.user_id = user_id

    async def process_command(self, command: str) -> dict:
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

        text = await chat_completion(prompt)
        if text is None:
            return {"response": "AI desk is not available. Check GEMINI_API_KEY configuration.", "action": None}
        try:
            parsed = json.loads(text.replace("```json", "").replace("```", "").strip())
            return parsed
        except Exception as e:
            logger.error(f"AI desk parse error: {e}", exc_info=True)
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
