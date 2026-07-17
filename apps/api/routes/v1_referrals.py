import logging
import secrets
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.db import async_supabase, get_supabase
from core.deps import get_current_user
from core.models import UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/referrals", tags=["referrals"])


class ReferralCodeResponse(BaseModel):
    referral_code: str


class ReferralStatsResponse(BaseModel):
    referral_code: str
    total_referrals: int
    completed_referrals: int
    rewards_earned: int


@router.get("/code", response_model=ReferralCodeResponse)
async def get_referral_code(user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    profile = supabase.table("profiles").select("referral_code").eq("id", user.id).execute()
    if profile.data and profile.data[0].get("referral_code"):
        return ReferralCodeResponse(referral_code=profile.data[0]["referral_code"])

    code = secrets.token_hex(4).upper()
    supabase.table("profiles").update({"referral_code": code}).eq("id", user.id).execute()
    return ReferralCodeResponse(referral_code=code)


@router.post("/generate-code", response_model=ReferralCodeResponse)
async def generate_referral_code(user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    code = secrets.token_hex(4).upper()
    supabase.table("profiles").update({"referral_code": code}).eq("id", user.id).execute()
    return ReferralCodeResponse(referral_code=code)


@router.get("/stats", response_model=ReferralStatsResponse)
async def referral_stats(user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    profile = supabase.table("profiles").select("referral_code").eq("id", user.id).execute()
    code = profile.data[0].get("referral_code", "") if profile.data else ""

    refs = supabase.table("referrals").select("status").eq("referrer_id", user.id).execute()
    all_refs = refs.data or []
    total = len(all_refs)
    completed = sum(1 for r in all_refs if r["status"] == "completed")
    rewards = completed

    return ReferralStatsResponse(
        referral_code=code,
        total_referrals=total,
        completed_referrals=completed,
        rewards_earned=rewards,
    )


@router.get("/list")
async def referral_list(user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    refs = supabase.table("referrals").select("*").eq("referrer_id", user.id).order("created_at", desc=True).execute()
    return {"referrals": refs.data or []}
