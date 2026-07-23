from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ai.desk import AIDesk
from ai.journal import AIJournal
from ai.copilot import AICopilot
from ai.chat import AIChatRouter
from ai.strategy_builder import build_strategy_from_prompt
from core.deps import get_current_user, get_capabilities, require_feature
from core.models import UserProfile
from core.capabilities import Capabilities

router = APIRouter(prefix="/ai", tags=["ai"])


class CommandRequest(BaseModel):
    command: str


class CopilotRequest(BaseModel):
    messages: list[dict]


class BuildStrategyRequest(BaseModel):
    prompt: str


class ChatRequest(BaseModel):
    messages: list[dict]


@router.post("/chat")
async def ai_unified_chat(
    req: ChatRequest,
    current_user: UserProfile = Depends(get_current_user),
    caps: Capabilities = Depends(get_capabilities),
):
    if not req.messages:
        raise HTTPException(status_code=400, detail="Messages cannot be empty.")

    features = [f.replace("_allowed", "") for f in ("custom_strategy_dev", "builder", "backtest") if getattr(caps, f"{f}_allowed", False)]
    router = AIChatRouter(
        user_id=current_user.id,
        subscription_tier=current_user.subscription_tier or "free",
        capabilities=features,
    )

    route = await router.route(req.messages)
    intent = route.get("intent", "copilot")

    if intent == "desk":
        desk = AIDesk(current_user.id)
        last_msg = req.messages[-1]["content"]
        result = await desk.process_command(last_msg)
        return {
            "intent": "desk",
            "response": result.get("response", ""),
            "data": {
                "action": result.get("action"),
                "needs_confirmation": result.get("needs_confirmation", False),
                "params": result.get("params"),
            },
        }

    if intent == "build_strategy":
        if not caps.custom_strategy_dev_allowed:
            return {
                "intent": "copilot",
                "response": "Sir, AI Strategy Builder sirf Enterprise (Yearly ₹1,25,000) plan ke saath available hai. Kya main aapko Enterprise plan ke baare mein bata doon?",
                "data": None,
            }
        last_msg = req.messages[-1]["content"]
        result = await build_strategy_from_prompt(last_msg)
        if result is None:
            return {
                "intent": "copilot",
                "response": "Sorry, strategy generate nahi ho payi. Kripya zyada specific prompt dijiye (like 'EMA crossover with trailing SL for NIFTY').",
                "data": None,
            }
        return {
            "intent": "build_strategy",
            "response": f"Ye raha aapka strategy draft: **{result.get('name', 'AI Strategy')}**. Aap ise deploy kar sakte hain ya Builder mein edit kar sakte hain.",
            "data": {"strategy": result},
        }

    copilot = AICopilot(current_user.id)
    response = await copilot.chat(req.messages)
    return {
        "intent": "copilot",
        "response": response,
        "data": None,
    }


@router.post("/desk")
async def ai_desk_command(
    req: CommandRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    desk = AIDesk(current_user.id)
    result = await desk.process_command(req.command)
    return result


@router.get("/journal")
async def get_journal(
    lookback_days: int = 7,
    current_user: UserProfile = Depends(get_current_user),
):
    journal = AIJournal(current_user.id)
    result = await journal.analyze_trades(lookback_days=lookback_days)
    return result


@router.get("/journal/entries")
async def get_journal_entries(
    current_user: UserProfile = Depends(get_current_user),
):
    from core.db import get_supabase
    from core.safe_query import async_safe_execute
    supabase = get_supabase()
    data = await async_safe_execute(
        supabase.table("journal_entries").select("*").eq("user_id", current_user.id).order("created_at", desc=True).limit(50)
    )
    return {"entries": data or []}


@router.post("/copilot")
async def ai_copilot_chat(
    req: CopilotRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    copilot = AICopilot(current_user.id)
    response = await copilot.chat(req.messages)
    return {"response": response}


@router.post("/build-strategy")
async def ai_build_strategy(
    req: BuildStrategyRequest,
    current_user: UserProfile = Depends(require_feature("custom_strategy_dev")),
    caps: Capabilities = Depends(get_capabilities),
):
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")

    result = await build_strategy_from_prompt(req.prompt)
    if result is None:
        raise HTTPException(status_code=500, detail="AI failed to generate strategy. Try a more specific prompt.")

    return {
        "strategy": result,
        "note": "This is an AI-generated strategy draft. Review and deploy via the Strategy Builder.",
        "tier": caps.tier,
    }
