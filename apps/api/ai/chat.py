import json
import logging

from ai.openrouter import chat_completion
from ai.sales_context import get_sales_context

logger = logging.getLogger(__name__)

INTENT_PROMPT = """You are a router for TradeMetrix AI. Given the user's last message and conversation history, determine the user's intent.

Available intents:
1. "copilot" — General chat about markets, strategies, trading, account info, platform help, coaching, sales/pricing questions, etc. This is the DEFAULT.
2. "desk" — User wants to EXECUTE something on their account: check positions/funds/orders, square off, pause/resume strategy, check risk, place trade, check PnL. Usually contains action verbs like "show", "check", "square off", "place", "pause", "resume", "why rejected", "kyu reject", etc.
3. "build_strategy" — User wants AI to BUILD/CREATE/GENERATE a trading strategy from natural language description. Keywords: "bana de", "banao", "build strategy", "create strategy", "generate strategy", "strategy banao", "crossover banao", "strategy for", "make a strategy", "aalgo banao", "custom strategy".

USER CONTEXT:
{context}

CONVERSATION HISTORY:
{history}

Last user message: {message}

Respond with ONLY a JSON object:
{{"intent": "copilot|desk|build_strategy", "reasoning": "brief reason", "confidence": 0.0-1.0}}
"""


class AIChatRouter:
    def __init__(self, user_id: str, subscription_tier: str, capabilities: list[str]):
        self.user_id = user_id
        self.subscription_tier = subscription_tier
        self.capabilities = capabilities

    async def route(self, messages: list[dict]) -> dict:
        last_message = messages[-1]["content"] if messages else ""
        history = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
            for m in messages[:-1]
        )

        context = json.dumps({
            "user_id": self.user_id,
            "plan": self.subscription_tier,
            "can_build_strategy": "custom_strategy_dev" in self.capabilities,
        })

        prompt = INTENT_PROMPT.format(
            context=context,
            history=history or "No prior conversation.",
            message=last_message,
        )

        text = await chat_completion(prompt, max_tokens=200)
        if text is None:
            return {"intent": "copilot", "reasoning": "fallback", "confidence": 0.0}

        try:
            text = text.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(text)
            intent = parsed.get("intent", "copilot")
            if intent not in ("copilot", "desk", "build_strategy"):
                intent = "copilot"
            return parsed | {"intent": intent}
        except (json.JSONDecodeError, KeyError):
            return {"intent": "copilot", "reasoning": "parse fallback", "confidence": 0.0}
