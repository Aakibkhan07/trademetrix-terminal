"""Tests for POST /auth/google — GoTrue OAuth session exchange (2026-08-24).

Uses the shared conftest `client` fixture (ASGITransport, no lifespan) so the
app's engine loops/Supabase client are never started or torn down mid-suite.
"""

import pytest

from core.models import UserProfile


def _gotrue_user(provider="google", user_id="g1", email="g@gmail.com", full_name="G User"):
    return {
        "id": user_id,
        "email": email,
        "identities": [{"provider": provider}] if provider else [],
        "user_metadata": {"full_name": full_name, "name": full_name},
    }


from unittest.mock import AsyncMock, MagicMock


def _mock_http(gotrue_status=200, gotrue_body=None, profile_rows=None):
    http = MagicMock()
    verify = MagicMock(status_code=gotrue_status)
    verify.json = lambda: gotrue_body if gotrue_body is not None else {}
    rest = MagicMock(status_code=200)
    rest.json = lambda: profile_rows or []
    http.get = AsyncMock(side_effect=[verify, rest])
    http.post = AsyncMock()
    return http


async def _post_google(client, payload):
    return await client.post(
        "/api/v1/auth/google", json=payload,
        headers={"x-csrf-token": "test-csrf-token-32-chars-for-testing!!"},
    )


class TestGoogleExchange:
    @pytest.mark.asyncio
    async def test_exchanges_valid_gotrue_session(self, client, monkeypatch):
        app_client = client
        http = _mock_http(gotrue_body=_gotrue_user())
        monkeypatch.setattr("routes.v1_auth.get_http_client", AsyncMock(return_value=http))
        # module-level import in the route → patch the route module's reference
        monkeypatch.setattr("routes.v1_auth.create_access_token", lambda subject: f"api-jwt-{subject}")

        r = await _post_google(app_client, {"access_token": "gotrue-tok"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["access_token"].startswith("api-jwt-g1")
        assert body["user"]["id"] == "g1"

    @pytest.mark.asyncio
    async def test_rejects_non_google_identity(self, client, monkeypatch):
        app_client = client
        http = _mock_http(gotrue_body=_gotrue_user(provider="azure"))
        monkeypatch.setattr("routes.v1_auth.get_http_client", AsyncMock(return_value=http))

        r = await _post_google(app_client, {"access_token": "x"})
        assert r.status_code == 400
        assert "not linked to a Google identity" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_rejects_invalid_gotrue_token(self, client, monkeypatch):
        app_client = client
        http = _mock_http(gotrue_status=401, gotrue_body={})
        monkeypatch.setattr("routes.v1_auth.get_http_client", AsyncMock(return_value=http))

        r = await _post_google(app_client, {"access_token": "bogus"})
        assert r.status_code == 401
        assert "Invalid or expired OAuth session" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_creates_profile_when_missing(self, client, monkeypatch):
        app_client = client
        http = _mock_http(gotrue_body=_gotrue_user(), profile_rows=None)
        monkeypatch.setattr("routes.v1_auth.get_http_client", AsyncMock(return_value=http))

        r = await _post_google(app_client, {"access_token": "t"})
        assert r.status_code == 200
        assert http.post.await_count == 1
        args, kwargs = http.post.await_args
        assert "/rest/v1/profiles" in args[0]
        sent = kwargs["json"]
        assert sent["id"] == "g1" and sent["full_name"] == "G User"

    @pytest.mark.asyncio
    async def test_uses_existing_profile_when_present(self, client, monkeypatch):
        app_client = client
        row = {"id": "g1", "email": "g@gmail.com", "full_name": "Existing Name"}
        http = _mock_http(gotrue_body=_gotrue_user(), profile_rows=[row])
        monkeypatch.setattr("routes.v1_auth.get_http_client", AsyncMock(return_value=http))

        r = await _post_google(app_client, {"access_token": "t"})
        assert r.status_code == 200
        assert r.json()["user"]["full_name"] == "Existing Name"
        assert http.post.await_count == 0
