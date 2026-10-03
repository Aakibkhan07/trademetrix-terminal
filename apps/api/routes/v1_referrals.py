import logging
import secrets

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
    profile = await async_supabase(lambda: supabase.table("profiles").select("referral_code").eq("id", user.id).execute())
    if profile.data and profile.data[0].get("referral_code"):
        return ReferralCodeResponse(referral_code=profile.data[0]["referral_code"])

    code = secrets.token_hex(4).upper()
    await async_supabase(lambda: supabase.table("profiles").update({"referral_code": code}).eq("id", user.id).execute())
    return ReferralCodeResponse(referral_code=code)


@router.post("/generate-code", response_model=ReferralCodeResponse)
async def generate_referral_code(user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    for _ in range(3):
        code = secrets.token_hex(4).upper()
        existing = await async_supabase(lambda: supabase.table("profiles").select("id").eq("referral_code", code).limit(1).execute())
        if not existing.data:
            await async_supabase(lambda: supabase.table("profiles").update({"referral_code": code}).eq("id", user.id).execute())
            return ReferralCodeResponse(referral_code=code)
    raise HTTPException(status_code=500, detail="Failed to generate unique referral code")


@router.get("/stats", response_model=ReferralStatsResponse)
async def referral_stats(user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    profile = await async_supabase(lambda: supabase.table("profiles").select("referral_code").eq("id", user.id).execute())
    # `.get(key, default)` supplies the default only when the key is **absent** from the dict. A SQL
    # NULL arrives as the key present with the value `None`, so the default never applied and
    # `referral_code=None` was handed to a `str` field, which pydantic rejects:
    #
    #     ValidationError: 1 validation error for ReferralStatsResponse
    #     referral_code  Input should be a valid string [type=string_type, input_value=None]
    #
    # Every user without a generated code has `referral_code IS NULL` — measured at 1 of 1 rows on a
    # clean database — so this was a 500 for essentially every caller, on the endpoint the Referral
    # System tab reads. `/referrals/code` next door gets this right with a truthiness check, because
    # there a missing code is meant to trigger generation.
    #
    # An empty string is the honest value here: this endpoint reports, it does not mint. Generating a
    # code as a side effect of reading stats would be the wrong verb for the wrong reason.
    code = (profile.data[0].get("referral_code") or "") if profile.data else ""

    refs = await async_supabase(lambda: supabase.table("referrals").select("status").eq("referrer_id", user.id).execute())
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
    refs = await async_supabase(lambda: supabase.table("referrals").select("*").eq("referrer_id", user.id).order("created_at", desc=True).execute())
    return {"referrals": refs.data or []}
