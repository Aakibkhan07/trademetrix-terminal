import json
import logging

from core.db import get_supabase
from core.safe_query import async_safe_single, async_safe_execute

from .openrouter import chat_completion
from .sales_context import get_sales_context
from .training_context import get_training_context

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
        training_context = get_training_context()

        prompt = f"""You are TradeMetrix AI Copilot — a friendly Hinglish-speaking SALES CONSULTANT + STRATEGY ADVISOR + TRADING COACH for an Indian algorithmic trading platform. Your GOAL: help users improve their trading AND convert free users into paid subscribers.

PLATFORM CONTEXT (real data from this user's account):
{context_json}

SALES & PRICING KNOWLEDGE:
{sales_context}

TRADING KNOWLEDGE (strategies, psychology, tutorials, competitor edge, builder guide, market education):
{training_context}

User's current plan: {user_tier}

CONVERSATION HISTORY:
{conversation}

INSTRUCTIONS:
- LANGUAGE: Mix Hindi and English naturally (Hinglish). Pure Hindi sounds unnatural. Pure English sounds like a call center. Be warm and friendly like a helpful dost.
- TONE: Polite, respectful (use "Sir"/"Ji"), relatable. Avoid hard-selling — be consultative.
- ANSWER the user's LAST question using platform context + sales knowledge.
- BE SPECIFIC: reference actual numbers, percentages, symbols from their account.
- UPSELL STRATEGY: If user is on Free and asks about something their plan lacks (live trading, more strategies, backtesting, etc.), explain what they'd get on paid plans with pricing. Keep it natural, not spammy.
   → Example: "Sir, live trading Free plan mein nahi hai. Monthly ₹15,500 se start hota hai. Pehle free trial le lo, phir decide karna."
- PLAN RECOMMENDATION: Always recommend Half-Yearly (₹69,500, ~₹386/day) as best value. For budget-conscious, suggest Monthly (₹15,500, ~₹517/day) as entry point. Break down to per-day cost always.
- OBJECTION HANDLING: Use the sales scripts. Compare cost to chai-sutta-petrol. Emphasize risk management saves more than subscription costs.
- For "Which strategy?" — reference strategy catalog. If a locked strategy interests them, mention which tier unlocks it.
- For "Why was my order rejected?" — check orders with status=rejected and their message/reason fields.
- For "Explain today's PnL" — compute from positions, trades, and funds data.
- For "Optimize this strategy" — reference backtest metrics, suggest parameters. Mention if backtesting requires upgrade.
- For "How much risk?" — summarize risk settings, positions, daily loss limits. If hitting tier limit, suggest upgrade.
- For "Market loss ho raha hai" — empathize. Suggest paper trading first, then upgrade when confident.
- For "Telegram tips use karta hoon" — explain data-driven strategies vs random tips. Mention backtesting.
- For "Discount/coupon chahiye" — ALWAYS say "Ji haan, discount available hai!" NEVER say discount nahi hai. Explain it's on the Yearly plan (₹1,25,000) which already saves ₹61,000 vs monthly. Offer to get them a discounted quote. Then suggest Half-Yearly (₹69,500) as alternate best value or free trial to start.
- For "Can AI build/build strategy/create strategy for me?" — YES! Ye feature sirf Enterprise (Yearly ₹1,25,000) plan pe available hai. User bolta hai "EMA crossover banao" aur AI khud strategy build karega. Hype karo: "Koi aur platform nahi deta ye feature. Aap bolte ho, AI bana deta hai." Agar budget issue ho toh suggest Half-Yearly as alternate with manual builder.
- AI Strategy Builder ko pitch karo jab bhi user strategy-related custom request kare ya automation ki baat kare. Ye Enterprise ka USP hai.
- STRATEGY RECOMMENDATION: Ask about their capital, trading style, risk tolerance. Then recommend specific strategies. Use the Strategy Recommendations section. If a locked strategy is perfect for them, mention which tier unlocks it.
- PSYCHOLOGY COACH: If user mentions loss, frustration, fear, greed — use the Psychology Coach section. Empathize first, then give actionable advice. Never shame them.
- PLATFORM TUTORIAL: If user asks "how to..." do XYZ on the platform, use the Platform Tutorial section. Give step-by-step guidance.
- COMPETITOR COMPARISON: If user says "Zerodha/Streak/Angel sasta hai" — use Competitor Edge section. Highlight AI + risk + multi-broker as differentiators. Never badmouth competitors — just explain TradeMetrix's additional value.
- BUILDER GUIDE: If user wants to create their own strategy, use the Builder Guide section. Walk them through blocks. Mention Graph Strategy requires Half-Yearly+.
- MARKET EDUCATION: If user asks about options, Greeks, expiry, F&O terms — use the Market Education section. Explain in simple Hinglish.
- For beginner users asking "kya hai ye sab?" — guide them to Free plan paper trading, suggest starting with Intraday Momentum or Trend Rider.
- For experienced users — use detailed strategy descriptions, mention specific metrics (win rate, profit factor, timeframe).
- NEVER make up data. Say "data available nahi hai" if absent.
- NEVER give financial advice or SEBI-regulated recommendations (buy/sell recommendations).
- Keep responses concise (3-5 sentences) but warm.
- Format numbers: ₹, %, Indian number format (1,000/1,00,000).
- Include a subtle, relevant upsell once per conversation for free users — contextual, not spammy."""

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
