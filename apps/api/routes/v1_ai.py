from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ai.desk import AIDesk
from ai.journal import AIJournal
from core.deps import get_current_user
from core.models import UserProfile

router = APIRouter(prefix="/ai", tags=["ai"])


class CommandRequest(BaseModel):
    command: str


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
    from core.safe_query import safe_execute
    supabase = get_supabase()
    data = safe_execute(
        supabase.table("journal_entries").select("*").eq("user_id", current_user.id).order("created_at", desc=True).limit(50)
    )
    return {"entries": data or []}
