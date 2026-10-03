"""`POST /api/v1/auth/change-password` refused nothing, and reported GoTrue's reasons as outages.

Both defects were found by driving the endpoint, not by reading it.

The first: `ChangePasswordRequest` validated nothing. Signup refuses anything under 8 characters or
missing an upper case letter, a digit or a symbol, but the new password went straight to the
Supabase admin API, which does not apply that policy either. Measured against a live Supabase: a six
character password was accepted with 200 and then signed in successfully — on an account created
under the eight character rule. The endpoint was a way to *downgrade* an account.

The second: the blanket `!= 200 -> 500`. GoTrue answers a rejected password with

    422 {"error_code": "weak_password", "msg": "Password should be at least 6 characters."}

and that arrived as `500 "Failed to update password"`. A client error reported as a server fault,
with the one useful part of the response discarded.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from routes.v1_auth import _upstream_detail, _upstream_status

COMPLIANT = "Str0ng&Pass!"

# Two things the `client` fixture sets up but does not send: the CSRF cookie needs its matching
# header, and `get_current_user` is overridden to require an `Authorization: Bearer` value. Routes
# that are unauthenticated (signup, signin) need neither, which is why test_auth.py posts to them
# with no headers at all and why every endpoint test here came back 403, then 401, until it did.
_HEADERS = {
    "x-csrf-token": "test-csrf-token-32-chars-for-testing!!",
    "authorization": "Bearer test-token",
}


def _resp(status_code: int, body=None, raises: bool = False) -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    if raises:
        r.json.side_effect = ValueError("not json")
    else:
        r.json.return_value = body
    return r


def _client(signin=200, update=200, update_body=None, update_raises=False) -> MagicMock:
    c = AsyncMock()
    c.post.return_value = _resp(signin, {"access_token": "x"})
    c.put.return_value = _resp(update, update_body if update_body is not None else {"id": "u"},
                               raises=update_raises)
    return c


class TestUpstreamStatus:
    @pytest.mark.parametrize("code", [400, 401, 403, 404, 409, 422])
    def test_client_errors_are_reported_as_client_errors(self, code):
        """4xx from upstream means our caller sent something we could not accept."""
        assert _upstream_status(code) == 400

    @pytest.mark.parametrize("code", [500, 502, 503])
    def test_server_errors_become_gateway_failures(self, code):
        """A 5xx is the only thing that is genuinely our problem to report as an outage."""
        assert _upstream_status(code) == 502

    def test_the_rejected_password_case_is_no_longer_a_500(self):
        """The exact status GoTrue returned for the weak password that started this."""
        assert _upstream_status(422) != 502


class TestUpstreamDetail:
    def test_gotrue_msg_is_the_part_worth_showing(self):
        body = {"code": 422, "error_code": "weak_password",
                "msg": "Password should be at least 6 characters.",
                "weak_password": {"reasons": ["length"]}}
        assert _upstream_detail(_resp(422, body), "fallback") == \
            "Password should be at least 6 characters."

    def test_non_json_body_falls_back(self):
        assert _upstream_detail(_resp(502, raises=True), "fallback") == "fallback"

    def test_blank_message_falls_back(self):
        assert _upstream_detail(_resp(422, {"msg": "   "}), "fallback") == "fallback"

    def test_list_body_falls_back(self):
        assert _upstream_detail(_resp(422, ["nope"]), "fallback") == "fallback"


class TestChangePasswordPolicy:
    @pytest.mark.asyncio
    async def test_six_characters_is_refused(self, client, monkeypatch):
        """The downgrade path. Six characters is what the old UI advertised as acceptable."""
        c = _client()
        monkeypatch.setattr("routes.v1_auth.get_http_client", AsyncMock(return_value=c))

        r = await client.post("/api/v1/auth/change-password", headers=_HEADERS, json={
            "current_password": "whatever", "new_password": "sixchr6"})

        assert r.status_code == 422
        assert "8 characters" in r.json()["detail"]
        # and the admin API was never reached — no weak password is even offered to it
        c.put.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("password,expected", [
        ("Str0ngPassw0rd", "special character"),
        ("str0ng&pass!", "uppercase"),
        ("STR0NG&PASS!", "lowercase"),
        ("Strong&Passy", "digit"),
    ])
    async def test_the_whole_signup_policy_applies(self, client, monkeypatch, password, expected):
        """Same rules signup enforces, so a change cannot end up weaker than the original signup."""
        c = _client()
        monkeypatch.setattr("routes.v1_auth.get_http_client", AsyncMock(return_value=c))

        r = await client.post("/api/v1/auth/change-password", headers=_HEADERS, json={
            "current_password": "whatever", "new_password": password})

        assert r.status_code == 422
        assert expected in r.json()["detail"]
        c.put.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_compliant_password_still_reaches_the_admin_api(self, client, monkeypatch):
        """The policy must not become a blanket refusal."""
        c = _client()
        monkeypatch.setattr("routes.v1_auth.get_http_client", AsyncMock(return_value=c))

        r = await client.post("/api/v1/auth/change-password", headers=_HEADERS, json={
            "current_password": "current-one", "new_password": COMPLIANT})

        assert r.status_code == 200
        c.put.assert_called_once()
        assert c.put.call_args.kwargs["json"]["password"] == COMPLIANT


class TestChangePasswordErrorReporting:
    @pytest.mark.asyncio
    async def test_gotrue_rejection_is_400_with_the_reason(self, client, monkeypatch):
        body = {"code": 422, "error_code": "weak_password",
                "msg": "Password should be at least 6 characters."}
        c = _client(update=422, update_body=body)
        monkeypatch.setattr("routes.v1_auth.get_http_client", AsyncMock(return_value=c))

        r = await client.post("/api/v1/auth/change-password", headers=_HEADERS, json={
            "current_password": "current-one", "new_password": COMPLIANT})

        assert r.status_code == 400
        assert r.json()["detail"] == "Password should be at least 6 characters."

    @pytest.mark.asyncio
    async def test_upstream_outage_is_502(self, client, monkeypatch):
        c = _client(update=503, update_body={}, update_raises=True)
        monkeypatch.setattr("routes.v1_auth.get_http_client", AsyncMock(return_value=c))

        r = await client.post("/api/v1/auth/change-password", headers=_HEADERS, json={
            "current_password": "current-one", "new_password": COMPLIANT})

        assert r.status_code == 502

    @pytest.mark.asyncio
    async def test_wrong_current_password_is_still_400(self, client, monkeypatch):
        """Ordering matters: the current password is checked before the new one is judged."""
        c = _client(signin=400)
        monkeypatch.setattr("routes.v1_auth.get_http_client", AsyncMock(return_value=c))

        r = await client.post("/api/v1/auth/change-password", headers=_HEADERS, json={
            "current_password": "wrong-one", "new_password": COMPLIANT})

        assert r.status_code == 400
        assert r.json()["detail"] == "Current password is incorrect"
        c.put.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_bad_current_password_still_wins_over_a_weak_new_one(self, client, monkeypatch):
        """The current password is verified first, and that ordering is deliberate.

        Reporting "your new password is too weak" to a caller who has not proved they own the
        account would confirm the current password was accepted. So with both wrong, the caller is
        told only that the current password is incorrect, and the new one is never judged.
        """
        c = _client(signin=400)
        monkeypatch.setattr("routes.v1_auth.get_http_client", AsyncMock(return_value=c))

        r = await client.post("/api/v1/auth/change-password", headers=_HEADERS, json={
            "current_password": "wrong-one", "new_password": "short1A"})

        assert r.status_code == 400
        assert r.json()["detail"] == "Current password is incorrect"
        assert "8 characters" not in r.json()["detail"]
        c.put.assert_not_called()