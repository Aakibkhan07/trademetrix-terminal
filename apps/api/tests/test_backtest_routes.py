"""Tests for backtest API routes.

Covers:
- GET /backtests/ — 401 unauth, 200 auth with empty list
- GET /backtests/{run_id} — 401 unauth, 404 for nonexistent
- POST /backtests/ — 401 unauth
- Existing endpoints not broken
"""

import pytest


class TestListBacktests:
    @pytest.mark.asyncio
    async def test_unauth_returns_401(self, client):
        resp = await client.get("/api/v1/backtests/")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"

    @pytest.mark.asyncio
    async def test_auth_returns_empty_list(self, client, auth_headers):
        resp = await client.get("/api/v1/backtests/", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "backtests" in data
        assert data["backtests"] == []


class TestGetBacktest:
    @pytest.mark.asyncio
    async def test_unauth_returns_401(self, client):
        resp = await client.get("/api/v1/backtests/nonexistent-id")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"

    @pytest.mark.asyncio
    async def test_nonexistent_returns_404(self, client, auth_headers):
        resp = await client.get("/api/v1/backtests/nonexistent-id", headers=auth_headers)
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        assert "not found" in resp.json()["detail"].lower()


class TestCreateBacktest:
    @pytest.mark.asyncio
    async def test_unauth_returns_403_csrf(self, client):
        resp = await client.post("/api/v1/backtests/", json={"strategy_type": "test"})
        assert resp.status_code == 403, f"Expected 403 (CSRF), got {resp.status_code}: {resp.text}"


class TestExistingEndpoints:
    @pytest.mark.asyncio
    async def test_strategies_still_works(self, client):
        resp = await client.get("/api/v1/backtests/strategies")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "strategies" in data
