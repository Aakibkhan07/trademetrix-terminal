import asyncio
import uuid
from collections.abc import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_asyncio import fixture as async_fixture

_TEST_CSRF_TOKEN = "test-csrf-token-32-chars-for-testing!!"

# In-memory risk state shared across risk tests
_risk_settings_db: dict[str, dict] = {}

# Session auth token cache
_SESSION_AUTH: dict | None = None
_MOCKS_APPLIED = False


def _apply_test_mocks():
    global _MOCKS_APPLIED, _SESSION_AUTH
    if _MOCKS_APPLIED:
        return _SESSION_AUTH
    _MOCKS_APPLIED = True

    from main import app
    from core.deps import get_current_user
    from core.models import UserProfile
    from core.security import create_access_token

    test_user_id = str(uuid.uuid4())
    test_email = f"ses_{test_user_id[:8]}@test.example.com"

    _risk_settings_db[test_user_id] = {
        "user_id": test_user_id,
        "kill_switch_enabled": False,
        "is_live": False,
        "max_daily_loss": 5000,
        "max_open_positions": 10,
        "max_position_size": 100000,
        "max_capital": 500000,
        "max_drawdown_pct": 20,
        "daily_profit_target": 0,
        "max_trades_per_day": 10,
        "max_symbol_exposure": 0,
        "max_account_exposure": 0,
        "trading_start": "09:15",
        "trading_end": "15:30",
        "allow_warning": True,
    }

    from fastapi import Request

    async def _override_get_current_user(request: Request):
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return UserProfile(
                id=test_user_id,
                email=test_email,
                full_name="Test User",
                subscription_tier="enterprise",
            )
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    app.dependency_overrides[get_current_user] = _override_get_current_user

    # ── Patch riskguard DB functions ──
    import risk.riskguard as rg

    async def mock_single(query_builder):
        entry = _risk_settings_db.get(test_user_id)
        return dict(entry) if entry else None

    async def mock_insert(table, data):
        if table == "risk_settings":
            uid = data.get("user_id", test_user_id)
            _risk_settings_db[uid] = dict(data)
            return {"id": "mock-id", **_risk_settings_db[uid]}
        return None

    async def mock_update(table, data, match_field, match_value):
        if table == "risk_settings":
            uid = match_value if match_field == "user_id" else test_user_id
            entry = _risk_settings_db.get(uid, {})
            entry.update(data)
            _risk_settings_db[uid] = entry
            return {"id": "mock-id"}
        return None

    async def mock_execute(query_builder):
        return []

    patch.object(rg, "async_safe_single", mock_single).start()
    patch.object(rg, "async_safe_insert", mock_insert).start()
    patch.object(rg, "async_safe_update", mock_update).start()
    patch.object(rg, "async_safe_execute", mock_execute).start()

    # ── Patch strategies Supabase ──
    import routes.v1_strategies as strat_routes

    strat_mock_sb = MagicMock()
    strat_mock_table = MagicMock()
    strat_mock_sb.table.return_value = strat_mock_table
    strat_mock_select = MagicMock()
    strat_mock_table.select.return_value = strat_mock_select
    strat_mock_select.eq.return_value = strat_mock_select
    strat_mock_execute = MagicMock()
    strat_mock_select.execute.return_value = strat_mock_execute
    strat_mock_execute.data = [
        {"id": "mock-strategy-id", "name": "Test Strategy", "user_id": test_user_id, "type": "builtin"}
    ]
    strat_mock_table.insert.return_value = strat_mock_select
    patch.object(strat_routes, "get_supabase", return_value=strat_mock_sb).start()

    # ── Patch auth HTTP client ──
    import routes.v1_auth as auth_routes

    mock_client = MagicMock()

    async def _mock_post(url, *args, **kwargs):
        url_str = str(url)
        if "/auth/v1/admin/users" in url_str:
            resp = MagicMock(status_code=200)
            resp.json.return_value = {"id": test_user_id, "email": test_email}
            return resp
        if "/auth/v1/token" in url_str:
            resp = MagicMock(status_code=401)
            resp.json.return_value = {"error": "Invalid credentials"}
            return resp
        resp = MagicMock(status_code=200)
        resp.json.return_value = {}
        return resp

    async def _mock_get(url, *args, **kwargs):
        url_str = str(url)
        if "/rest/v1/profiles" in url_str:
            resp = MagicMock(status_code=200)
            resp.json.return_value = [{"id": test_user_id, "email": test_email}]
            return resp
        resp = MagicMock(status_code=200)
        resp.json.return_value = {}
        return resp

    mock_client.post = _mock_post
    mock_client.get = _mock_get

    async def _mock_get_http_client():
        return mock_client

    patch.object(auth_routes, "get_http_client", _mock_get_http_client).start()

    _SESSION_AUTH = {
        "Authorization": f"Bearer {create_access_token(subject=test_user_id)}",
        "x-csrf-token": _TEST_CSRF_TOKEN,
    }
    return _SESSION_AUTH


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@async_fixture
async def client() -> AsyncGenerator:
    from httpx import ASGITransport, AsyncClient

    from main import app

    _apply_test_mocks()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.cookies.set("csrf_token", _TEST_CSRF_TOKEN)
        yield ac


@async_fixture(scope="session")
async def auth_headers() -> dict:
    global _SESSION_AUTH
    if _SESSION_AUTH is not None:
        return _SESSION_AUTH
    _SESSION_AUTH = _apply_test_mocks()
    return _SESSION_AUTH
