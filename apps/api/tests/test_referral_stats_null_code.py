"""A NULL column must not become a 500.

## The bug

`GET /referrals/stats` answered **500** for essentially every caller:

    ValidationError: 1 validation error for ReferralStatsResponse
    referral_code
      Input should be a valid string [type=string_type, input_value=None, input_type=NoneType]

The line was

    code = profile.data[0].get("referral_code", "") if profile.data else ""

`dict.get(key, default)` returns the default only when the key is **absent**. A SQL `NULL` arrives
with the key *present* and the value `None`, so the default never applied, and `None` was handed to a
`str` field.

`profiles.referral_code` is NULL until `/referrals/code` is called, and nothing else populates it —
measured at **1 of 1** rows on a clean database. So the endpoint was broken for every user who had
not visited that page, and it returned 500 rather than an empty string, so nothing degraded
gracefully.

The neighbouring `GET /referrals/code` gets this right, because there a missing code is *meant* to
trigger generation and a truthiness check is what you want. This endpoint only reports.

## Why it went unnoticed

The page that reads it, the admin Referral System tab, calls a path that does not exist —
`/admin/referrals/stats` — so it was already 404ing before this response ever mattered. Fixing the
frontend path without fixing this would have turned a silent empty tab into a visible 500.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from routes.v1_referrals import ReferralStatsResponse


def _response(**over):
    base = dict(referral_code="", total_referrals=0, completed_referrals=0, rewards_earned=0)
    base.update(over)
    return base


def _table(name: str, profile_row, ref_rows):
    """A supabase table stub whose `.data` is what the route reads."""
    t = MagicMock()
    chain = MagicMock()
    t.select.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    if name == "profiles":
        chain.execute.return_value = MagicMock(data=profile_row)
    elif name == "referrals":
        chain.execute.return_value = MagicMock(data=ref_rows)
    else:
        chain.execute.return_value = MagicMock(data=[])
    return t


async def _call_stats(profile_row, ref_rows):
    from routes.v1_referrals import referral_stats

    supabase = MagicMock()
    supabase.table.side_effect = lambda n: _table(n, profile_row, ref_rows)

    user = MagicMock()
    user.id = "u1"

    with patch("routes.v1_referrals.get_supabase", return_value=supabase), \
         patch("routes.v1_referrals.async_supabase", side_effect=lambda c, *a, **k: c()):
        return await referral_stats(user)


# ── the crash ───────────────────────────────────────────────────────────────────

async def test_a_null_referral_code_does_not_500():
    """The exact production shape: the row exists, the column is SQL NULL.

    This is what the database returns for a user who has never opened the referral page.
    """
    out = await _call_stats(profile_row=[{"referral_code": None}], ref_rows=[])

    assert out.referral_code == ""
    assert out.total_referrals == 0


async def test_the_response_model_rejects_none_but_accepts_empty_string():
    """Pins *why* this is a bug rather than a style choice.

    If `str` ever stopped rejecting `None` the original line would look fine again, and the test
    above would be the only thing standing between this and a silent regression.
    """
    with pytest.raises(Exception):
        ReferralStatsResponse(
            referral_code=None,  # type: ignore[arg-type]
            total_referrals=0,
            completed_referrals=0,
            rewards_earned=0,
        )

    assert ReferralStatsResponse(
        referral_code="", total_referrals=0, completed_referrals=0, rewards_earned=0
    ).referral_code == ""


# ── the paths that already worked, which must keep working ───────────────────────

async def test_a_real_code_is_passed_through():
    out = await _call_stats(profile_row=[{"referral_code": "AB12CD34"}], ref_rows=[])
    assert out.referral_code == "AB12CD34"


async def test_an_absent_key_is_still_an_empty_string():
    out = await _call_stats(profile_row=[{}], ref_rows=[])
    assert out.referral_code == ""


async def test_no_profile_row_at_all():
    out = await _call_stats(profile_row=[], ref_rows=[])
    assert out.referral_code == ""


async def test_counts_still_come_from_the_referrals_table():
    rows = [{"status": "completed"}, {"status": "completed"}, {"status": "pending"}]
    out = await _call_stats(profile_row=[{"referral_code": None}], ref_rows=rows)

    assert out.total_referrals == 3
    assert out.completed_referrals == 2
    assert out.rewards_earned == 2


async def test_reading_stats_does_not_generate_a_code():
    """Reporting must not mint.

    `/referrals/code` exists to generate a code and correctly does so on a truthiness check. Doing it
    here too would be the wrong verb for the wrong reason — a read that writes.
    """
    supabase = MagicMock()
    updates: list = []
    t = _table("profiles", [{"referral_code": None}], [])

    def _track(name):
        if name == "profiles":
            t.update.return_value.eq.return_value.execute.side_effect = lambda: updates.append(1)
            return t
        return _table(name, [], [])

    supabase.table.side_effect = _track

    from routes.v1_referrals import referral_stats

    user = MagicMock()
    user.id = "u1"
    with patch("routes.v1_referrals.get_supabase", return_value=supabase), \
         patch("routes.v1_referrals.async_supabase", side_effect=lambda c, *a, **k: c()):
        out = await referral_stats(user)

    assert out.referral_code == ""
    assert not updates, "reading stats must not write a referral code to the profile"