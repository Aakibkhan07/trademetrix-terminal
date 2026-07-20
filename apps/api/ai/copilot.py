import json
import logging

from core.db import get_supabase
from core.safe_query import async_safe_single, async_safe_execute

from .openrouter import chat_completion
from .sales_context import get_sales_context

logger = logging.getLogger(__name__)

CONTEXT_SECTIONS: list[str] = [
    "profile", "positions", "funds", "orders", "risk",
    "strategies", "runs", "journal", "backtests", "market",
]


class AICopilot:
    def __init__(self, user_id: str):
        self.user_id = user_id

    async def chat(self, messages: list[dict]) -> str:
        context = await self._build_context()
        context_json = json.dumps(context, indent=2, default=str)

        conversation = "\n".join(
            f"{'User' if m.get('role') == 'user' else 'Assistant'}: {m['content']}"
            for m in messages[-20:]
        )

        user_tier = context.get("profile", {}).get("subscription_tier", "free") or "free"
        sales_context = get_sales_context()

        prompt = f"""You are the TradeMetrix AI Copilot — a technical assistant and SALES CONSULTANT for an algorithmic trading platform. Your GOAL is to help users and convert free users into paid subscribers when appropriate.

PLATFORM CONTEXT (real data from this user's account):
{context_json}

SALES & PRICING KNOWLEDGE:
{sales_context}

User's current plan: {user_tier}

CONVERSATION HISTORY:
{conversation}

INSTRUCTIONS:
- Answer the user's LAST question using the platform context and sales knowledge above.
- Be specific. Reference actual numbers, symbols, percentages from the context.
- If the context lacks data to answer fully, say so clearly.
- IDENTIFY UPSELL OPPORTUNITIES: If a user on Free asks for something their plan doesn't include (live trading, more strategies, backtesting etc.), clearly explain what they'd get by upgrading and mention pricing. E.g. "Live trading is available on paid plans starting from ₹15,500/month."
- For "Which plan should I get?" — recommend Half-Yearly (₹69,500) as best value. Break down to ₹386/day.
- Objection handling: If user says "too expensive", break down daily cost. If they compare with competitors, highlight AI + risk management + multi-broker advantage.
- For "Why was my order rejected?" — check orders with status=rejected and their message/reason fields.
- For "Explain today's PnL" — compute from positions, trades, and funds data.
- For "Create an EMA crossover strategy" — explain the steps using the available strategy catalog and builder blocks.
- For "Optimize this strategy" — reference backtest metrics and suggest parameter ranges, and mention if backtesting requires an upgrade.
- For "How much risk am I taking?" — summarize risk settings, open positions, and daily loss limits. If they hit their tier limit, suggest upgrade for higher limits.
- For "Which strategy performed best?" — compare strategy runs by total_pnl or backtest results.
- For "Explain today's market" — use any market data, indices, or symbol info available.
- NEVER make up data. If data is absent, say "I don't have that data available."
- NEVER give financial advice or stock recommendations. You are a tool, not a registered advisor.
- Keep responses concise (2-5 sentences) but informative.
- Format numbers with appropriate units (%, ₹, $).
- If user has no active subscription (free tier), include a subtle, relevant upsell mention in your response once per conversation — not spammy, just contextual."""

        text = await chat_completion(prompt)
        if text is None:
            return "AI Copilot is not available. Configure GEMINI_API_KEY."
        text = text.replace("```json", "").replace("```", "").strip()
        return text

    async def _build_context(self) -> dict:
        supabase = get_supabase()
        context: dict = {}

        # Profile
        try:
            profile = await async_safe_single(
                supabase.table("profiles").select("id, email, full_name, subscription_tier, created_at").eq("id", self.user_id)
            )
            context["profile"] = profile or {}
        except Exception as e:
            logger.warning("Failed to fetch profile: %s", e)
            context["profile"] = {}

        # Positions
        try:
            positions = await async_safe_execute(
                supabase.table("positions_snapshot").select("*").eq("user_id", self.user_id)
            ) or []
            context["positions"] = positions
        except Exception as e:
            logger.warning("Failed to fetch positions: %s", e)
            context["positions"] = []

        # Funds
        try:
            funds = await async_safe_single(
                supabase.table("funds_snapshot").select("*").eq("user_id", self.user_id)
            )
            context["funds"] = funds or {}
        except Exception as e:
            logger.warning("Failed to fetch funds: %s", e)
            context["funds"] = {}

        # Orders (recent 50)
        try:
            orders = await async_safe_execute(
                supabase.table("orders").select("*").eq("user_id", self.user_id).order("created_at", desc=True).limit(50)
            ) or []
            if orders:
                for o in orders:
                    if isinstance(o.get("created_at"), str):
                        o["created_at"] = o["created_at"][:19]
                    if isinstance(o.get("filled_at"), str):
                        o["filled_at"] = o["filled_at"][:19]
            context["orders"] = orders[:20]
        except Exception as e:
            logger.warning("Failed to fetch orders: %s", e)
            context["orders"] = []

        # Risk settings
        try:
            risk = await async_safe_single(
                supabase.table("risk_settings").select("*").eq("user_id", self.user_id)
            )
            context["risk"] = risk or {}
        except Exception as e:
            logger.warning("Failed to fetch risk: %s", e)
            context["risk"] = {}

        # Strategies + assignments
        try:
            strategies = await async_safe_execute(
                supabase.table("strategies").select("*").eq("user_id", self.user_id)
            ) or []
            context["strategies"] = strategies
        except Exception as e:
            logger.warning("Failed to fetch strategies: %s", e)
            context["strategies"] = []

        try:
            assignments = await async_safe_execute(
                supabase.table("strategy_assignments").select("*").eq("user_id", self.user_id).eq("active", True)
            ) or []
            context["strategy_assignments"] = assignments
        except Exception as e:
            logger.warning("Failed to fetch assignments: %s", e)
            context["strategy_assignments"] = []

        # Strategy runs
        try:
            runs = await async_safe_execute(
                supabase.table("strategy_runs").select("*").eq("user_id", self.user_id).order("created_at", desc=True).limit(20)
            ) or []
            for r in runs:
                if isinstance(r.get("created_at"), str):
                    r["created_at"] = r["created_at"][:19]
            context["runs"] = runs
        except Exception as e:
            logger.warning("Failed to fetch runs: %s", e)
            context["runs"] = []

        # Journal entries
        try:
            entries = await async_safe_execute(
                supabase.table("journal_entries").select("*").eq("user_id", self.user_id).order("created_at", desc=True).limit(10)
            ) or []
            context["journal"] = entries
        except Exception as e:
            logger.warning("Failed to fetch journal: %s", e)
            context["journal"] = []

        # Backtest results
        try:
            backtests = await async_safe_execute(
                supabase.table("backtest_results").select("*").eq("user_id", self.user_id).order("created_at", desc=True).limit(10)
            ) or []
            context["backtests"] = backtests
        except Exception as e:
            logger.warning("Failed to fetch backtests: %s", e)
            context["backtests"] = []

        # Strategy catalog (available built-in strategies)
        try:
            from strategies import get_strategy_catalog
            catalog = get_strategy_catalog()
            context["strategy_catalog"] = [
                {"key": k, "name": v.get("name", k), "tier": v.get("tier", "free")}
                for k, v in catalog.items()
            ]
        except Exception as e:
            logger.warning("Failed to fetch catalog: %s", e)
            context["strategy_catalog"] = []

        # Broker info
        try:
            brokers = await async_safe_execute(
                supabase.table("broker_credentials").select("broker, is_active").eq("user_id", self.user_id)
            ) or []
            context["brokers"] = brokers
        except Exception as e:
            logger.warning("Failed to fetch brokers: %s", e)
            context["brokers"] = []

        return context
