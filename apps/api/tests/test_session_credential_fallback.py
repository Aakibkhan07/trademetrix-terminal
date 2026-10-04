"""A live session cookie must not be overruled by a dead bearer token.

The bearer header and the session cookie are two credentials for the same session with
different lifetimes: `COOKIE_MAX_AGE` is 7 days while `create_access_token` mints a token
for 24 hours. The frontend attaches the stored bearer on every request and never refreshes
it, so after 24 hours a signed-in browser presented an expired bearer *and* a valid cookie
and was refused. `get_optional_user` delegates to `get_current_user`, so the anonymous
analytics ingest inherited the same behaviour.

These tests assert the fallback on the resolution path itself rather than on a route, so
they hold for every endpoint that depends on `get_current_user`.
"""

import time
from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from core import deps
from core.deps import get_current_user, get_optional_user
from core.security import create_access_token, decode_access_token

USER_ID = "ec75b496-cdf7-4e2a-96da-96ed5454ec41"


class FakeCredentials:
    def __init__(self, credentials: str):
        self.credentials = credentials


class FakeRequest:
    def __init__(self, cookies: dict[str, str] | None = None):
        self.cookies = cookies or {}


def _profile_row() -> dict:
    return {"id": USER_ID, "email": "someone@example.com", "role": "user"}


async def _resolve(request, credentials):
    """Run get_current_user with only the profile lookup satisfied from its cache.

    `get_current_user` reads `_user_cache` before it queries Supabase, so seeding the cache
    short-circuits the database round-trip while leaving the part under test — candidate
    ordering and decode failures — fully real.
    """
    with patch("core.deps.UserProfile", side_effect=lambda **kw: kw):
        for token_owner in _users_referenced_by(request, credentials):
            deps._user_cache[token_owner] = (time.time(), _profile_row())
        try:
            return await get_current_user(request, credentials)
        finally:
            deps._user_cache.clear()


def _users_referenced_by(request, credentials) -> list[str]:
    """Every subject that could be resolved from these credentials."""
    subjects = []
    for candidate in [credentials.credentials if credentials else None, *request.cookies.values()]:
        if not candidate:
            continue
        payload = decode_access_token(candidate)
        if payload and payload.get("sub"):
            subjects.append(payload["sub"])
    return subjects


async def test_an_expired_bearer_does_not_discard_a_valid_session_cookie():
    """The regression: a live cookie must survive a dead bearer. 401 was the old answer."""
    valid = create_access_token(USER_ID)
    expired = create_access_token(USER_ID, expires_delta=timedelta(seconds=-60))

    resolved = await _resolve(FakeRequest({"tm_session": valid}), FakeCredentials(expired))

    assert resolved["id"] == USER_ID


async def test_a_valid_bearer_is_still_preferred_and_resolves():
    valid = create_access_token(USER_ID)
    other = create_access_token("00000000-0000-0000-0000-000000000000")

    resolved = await _resolve(FakeRequest({"tm_session": other}), FakeCredentials(valid))

    assert resolved["id"] == USER_ID


async def test_a_valid_cookie_alone_still_authenticates():
    """Unchanged behaviour: the cookie path was always correct."""
    valid = create_access_token(USER_ID)

    resolved = await _resolve(FakeRequest({"tm_session": valid}), None)

    assert resolved["id"] == USER_ID


async def test_no_credentials_at_all_is_still_unauthenticated():
    with pytest.raises(HTTPException) as exc:
        await _resolve(FakeRequest(), None)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Not authenticated"


async def test_every_credential_expired_is_still_unauthenticated():
    """The fallback must not turn a genuinely dead session into a valid one."""
    expired = create_access_token(USER_ID, expires_delta=timedelta(seconds=-60))

    with pytest.raises(HTTPException) as exc:
        await _resolve(FakeRequest({"tm_session": expired}), FakeCredentials(expired))
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid or expired token"


async def test_a_garbage_bearer_falls_back_to_the_cookie():
    """A corrupted localStorage value must not be able to sign the user out."""
    valid = create_access_token(USER_ID)

    resolved = await _resolve(FakeRequest({"tm_session": valid}), FakeCredentials("not-a-jwt"))

    assert resolved["id"] == USER_ID


async def test_the_legacy_access_token_cookie_is_still_accepted_as_a_fallback():
    """`access_token` is the pre-rename cookie name and is still read."""
    valid = create_access_token(USER_ID)

    resolved = await _resolve(
        FakeRequest({"access_token": valid}), FakeCredentials("not-a-jwt")
    )

    assert resolved["id"] == USER_ID


async def test_an_explicit_bearer_outranks_a_cookie_belonging_to_someone_else():
    """Precedence is deliberate, and it is security-relevant.

    A browser can hold a cookie from an earlier sign-in while the page issues a bearer for
    the current one. The explicit `Authorization` header is the caller's stated intent, so it
    must decide the identity — otherwise a stale cookie could answer for whoever signed in
    last on that browser rather than who the request claims to be.

    Found by mutation: reversing the candidate order left the suite fully green, because
    every other test uses one identity for both credentials. This pins it.
    """
    bearer_user = "11111111-1111-1111-1111-111111111111"
    cookie_user = "22222222-2222-2222-2222-222222222222"

    with patch("core.deps.UserProfile", side_effect=lambda **kw: kw):
        deps._user_cache[bearer_user] = (time.time(), {**_profile_row(), "id": bearer_user})
        deps._user_cache[cookie_user] = (time.time(), {**_profile_row(), "id": cookie_user})
        try:
            resolved = await get_current_user(
                FakeRequest({"tm_session": create_access_token(cookie_user)}),
                FakeCredentials(create_access_token(bearer_user)),
            )
        finally:
            deps._user_cache.clear()

    assert resolved["id"] == bearer_user


async def test_get_optional_user_inherits_the_fallback():
    """It delegates to get_current_user, so this is a wiring assertion."""
    valid = create_access_token(USER_ID)
    expired = create_access_token(USER_ID, expires_delta=timedelta(seconds=-60))

    with patch("core.deps.UserProfile", side_effect=lambda **kw: kw):
        deps._user_cache[USER_ID] = (time.time(), _profile_row())
        try:
            resolved = await get_optional_user(
                FakeRequest({"tm_session": valid}), FakeCredentials(expired)
            )
        finally:
            deps._user_cache.clear()

    assert resolved is not None
    assert resolved["id"] == USER_ID
