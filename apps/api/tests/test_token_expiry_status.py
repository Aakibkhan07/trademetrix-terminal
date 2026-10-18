"""A token that expired was still reported as `valid`.

Measured in production on 2026-10-18: user `fa668109`'s Fyers credential read

    token_status    = "valid"
    token_expires_at = 2026-09-23T00:30:00+00:00      (25 days in the past)

and the Fyers circuit breaker was open with 137 consecutive failures. The user is told their
broker is connected; every order they send fails; nothing in the UI tells them why.

The cause is that `token_status` is *written* as `"valid"` in three places
(`broker_repository.activate_broker`, `brokers.token_manager`, `engine.token_refresh`) and never
re-read against the expiry that sits next to it in the same row. So the stored status describes
what the token was when it was saved, not what it is now, and it is saved once and then believed
forever.

Nothing was reading it wrong. `get_token_status` returns the column, and
`BrokerRepository.list_credentials` returns the column, and both hand that to the UI as *the*
answer. Fixing the status where it is reported fixes every consumer at once; writing a cron to
flip the column instead would be a second source of truth that can rot on the same schedule the
token does.

These tests assert the derivation, not the plumbing: `effective_token_status` is pure, so the
interesting cases (timezone-naive strings, exactly-now, revocation beating expiry) are all
reachable without a database.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from engine.token_refresh import effective_token_status

PAST = "2026-09-23T00:30:00+00:00"
FUTURE = "2030-01-01T00:00:00+00:00"


def _expired_row(**over) -> dict:
    return {"token_status": "valid", "token_expires_at": PAST, **over}


class TestAStoredStatusCannotOutliveTheToken:
    def test_an_expired_token_is_not_reported_valid(self):
        status, expired = effective_token_status(_expired_row())
        assert status != "valid", (
            "a token that expired 25 days ago is still reported valid -- this is the "
            "production bug, exactly"
        )
        assert expired is True

    def test_the_row_still_says_valid_so_this_cannot_pass_via_a_seeded_fixture(self):
        """Guards the guard: the input must be the wrong value, not the right one."""
        assert _expired_row()["token_status"] == "valid"

    def test_a_live_token_is_still_valid(self):
        status, expired = effective_token_status(
            {"token_status": "valid", "token_expires_at": FUTURE})
        assert status == "valid"
        assert expired is False

    def test_a_token_that_expires_in_a_minute_is_not_yet_expired(self):
        soon = (datetime.now(UTC) + timedelta(minutes=1)).isoformat()
        status, expired = effective_token_status(
            {"token_status": "valid", "token_expires_at": soon})
        assert (status, expired) == ("valid", False)

    def test_a_token_that_expired_a_second_ago_is(self):
        just_gone = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        status, expired = effective_token_status(
            {"token_status": "valid", "token_expires_at": just_gone})
        assert (status, expired) == ("needs_attention", True)

    def test_the_boundary_is_now_not_later(self):
        """`>= now` would keep a token alive for an instant past its expiry."""
        exact = datetime.now(UTC).isoformat()
        _, expired = effective_token_status(
            {"token_status": "valid", "token_expires_at": exact})
        assert expired is True

    def test_a_timezone_naive_expiry_is_read_as_utc(self):
        """`fromisoformat` yields a naive datetime for a string without an offset.

        Comparing that to an aware `now()` raises TypeError, and a status read that raises is
        worse than one that lies -- so naive values are pinned to UTC rather than rejected.
        """
        naive = (datetime.now(UTC) - timedelta(days=2)).replace(tzinfo=None).isoformat()
        status, expired = effective_token_status(
            {"token_status": "valid", "token_expires_at": naive})
        assert (status, expired) == ("needs_attention", True)

    def test_a_future_naive_expiry_is_not_read_as_expired(self):
        naive = (datetime.now(UTC) + timedelta(days=2)).replace(tzinfo=None).isoformat()
        _, expired = effective_token_status(
            {"token_status": "valid", "token_expires_at": naive})
        assert expired is False


class TestExpiryDoesNotOverwriteAMoreSevereStatus:
    def test_revoked_stays_revoked(self):
        status, expired = effective_token_status(
            {"token_status": "revoked", "token_expires_at": PAST})
        assert status == "revoked", "a revoked token stays revoked whatever the clock says"

    def test_needs_attention_is_not_upgraded_by_a_future_expiry(self):
        status, _ = effective_token_status(
            {"token_status": "needs_attention", "token_expires_at": FUTURE})
        assert status == "needs_attention", (
            "a future expiry must not talk the system into calling a flagged credential healthy"
        )


class TestUnknownAndAbsent:
    def test_a_row_with_no_expiry_cannot_be_called_expired(self):
        """Several brokers store no expiry at all; absence is not evidence of death."""
        status, expired = effective_token_status({"token_status": "valid"})
        assert (status, expired) == ("valid", False)

    def test_a_row_with_no_status_reports_unknown(self):
        status, _ = effective_token_status({})
        assert status == "unknown"

    def test_an_unparseable_expiry_does_not_claim_expiry(self):
        status, expired = effective_token_status(
            {"token_status": "valid", "token_expires_at": "not-a-date"})
        assert (status, expired) == ("valid", False)

    def test_a_malformed_row_is_reported_rather_than_raised(self):
        """A status read that raises is worse than one that is wrong: it 500s the page."""
        assert effective_token_status({"token_expires_at": None}) == ("unknown", False)


class TestTheEndpointAppliesIt:
    """The endpoint, not just the pure function -- `get_token_status` is what the UI calls.

    The stub has to answer `.table().select().eq().eq().limit()`: the query chain is built
    before `async_safe_execute` is reached, so a bare object raises before the patch is even
    consulted. Stubbing too little here fails for a reason that has nothing to do with the test.
    """

    @staticmethod
    def _stub(monkeypatch, tr, rows):
        class _Q:
            def table(self, *_a): return self
            def select(self, *_a, **_k): return self
            def eq(self, *_a, **_k): return self
            def limit(self, *_a, **_k): return self

        async def fake_execute(_q):
            return rows

        monkeypatch.setattr(tr, "async_safe_execute", fake_execute)
        monkeypatch.setattr(tr, "get_supabase", lambda: _Q())

    @pytest.mark.asyncio
    async def test_get_token_status_derives_rather_than_echoes(self, monkeypatch):
        from engine import token_refresh as tr

        self._stub(monkeypatch, tr, [{"token_status": "valid", "token_expires_at": PAST,
                                      "last_token_refresh_at": None, "broker": "fyers"}])

        out = await tr.get_token_status("u", "fyers")
        assert out["status"] != "valid", "the endpoint still echoes the stored column"
        assert out["expired"] is True
        assert out["expires_at"] == PAST, "the raw expiry must still be reported alongside"

    @pytest.mark.asyncio
    async def test_a_missing_credential_still_reports_unknown(self, monkeypatch):
        from engine import token_refresh as tr

        self._stub(monkeypatch, tr, [])

        out = await tr.get_token_status("u", "fyers")
        assert out["status"] == "unknown"
        assert out.get("expired", False) is False

    @pytest.mark.asyncio
    async def test_a_live_token_is_still_reported_valid(self, monkeypatch):
        from engine import token_refresh as tr

        self._stub(monkeypatch, tr, [{"token_status": "valid", "token_expires_at": FUTURE,
                                      "last_token_refresh_at": None, "broker": "fyers"}])

        out = await tr.get_token_status("u", "fyers")
        assert out["status"] == "valid"
        assert out["expired"] is False


class TestTheBrokerListingAppliesIt:
    """The other consumer, and the one the `/brokers` page actually reads.

    Fixing `get_token_status` alone would leave the badge on the main brokers page still saying
    "valid" -- the same lie through a different door. Both go through one derivation so they
    cannot disagree.
    """

    @staticmethod
    def _rows(monkeypatch, repo_mod, rows):
        class _Q:
            def table(self, *_a): return self
            def select(self, *_a, **_k): return self
            def eq(self, *_a, **_k): return self

        async def fake_execute(_q):
            return rows

        async def fake_single(_q):
            return rows[0] if rows else None

        monkeypatch.setattr(repo_mod, "async_safe_execute", fake_execute)
        monkeypatch.setattr(repo_mod, "async_safe_single", fake_single)
        monkeypatch.setattr(repo_mod, "get_supabase", lambda: _Q())

    @pytest.mark.asyncio
    async def test_the_listing_derives_status_too(self, monkeypatch):
        from infrastructure.repositories import broker_repository as repo_mod

        self._rows(monkeypatch, repo_mod, [{
            "id": "1", "broker": "fyers", "role": "execution", "is_active": True,
            "token_status": "valid", "token_expires_at": PAST, "created_at": None,
        }])

        # SupabaseBrokerRepository, not the abstract base -- the derivation lives in the
        # concrete class and instantiating the ABC raises before any of this runs.
        out = await repo_mod.SupabaseBrokerRepository().list_credentials("u")
        assert out[0]["token_status"] != "valid", (
            "the /brokers page still shows an expired credential as valid"
        )
        assert out[0]["expired"] is True
        assert out[0]["stored_token_status"] == "valid", (
            "the recorded value must stay available rather than be overwritten away"
        )

    @pytest.mark.asyncio
    async def test_a_live_credential_is_untouched_by_the_derivation(self, monkeypatch):
        from infrastructure.repositories import broker_repository as repo_mod

        self._rows(monkeypatch, repo_mod, [{
            "id": "1", "broker": "dhan", "role": "execution", "is_active": True,
            "token_status": "valid", "token_expires_at": FUTURE, "created_at": None,
        }])

        # SupabaseBrokerRepository, not the abstract base -- the derivation lives in the
        # concrete class and instantiating the ABC raises before any of this runs.
        out = await repo_mod.SupabaseBrokerRepository().list_credentials("u")
        assert out[0]["token_status"] == "valid"
        assert out[0]["expired"] is False
        assert "stored_token_status" not in out[0], (
            "the shadow key is only added when the derived value differs from what was stored"
        )