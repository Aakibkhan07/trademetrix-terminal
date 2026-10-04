import asyncio
import uuid
from collections.abc import AsyncGenerator, Generator
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_asyncio import fixture as async_fixture

_TEST_CSRF_TOKEN = "test-csrf-token-32-chars-for-testing!!"

# In-memory risk state shared across risk tests
_risk_settings_db: dict[str, dict] = {}

# Session auth token cache
_SESSION_AUTH: dict | None = None
_MOCKS_APPLIED = False

#: Every patcher started by `_apply_test_mocks`, so they can be undone as a group.
#:
#: These mocks are applied **once for the whole session** and were never stopped. That is
#: deliberate for the 1157 tests that want them — the kill switch reads as off, the
#: database is in-memory, and re-applying per test would be pure overhead. The cost was
#: that there was no way to get the real behaviour back, and it has now silently broken
#: three tests:
#:
#: * `test_cache_counter_ttl.py` (c61b066) asserted against `_mock_cache_increment`, which
#:   returns a constant `1`. The file could not have caught a regression in the counter TTL.
#: * `test_otp_lockout.py` (2e8db2e) — same, for `increment`.
#: * `test_broker_credential_roles.py` (94e80cf) passed in isolation and failed in the full
#:   suite, because `risk.helpers.async_safe_execute` was stubbed out from under it.
#:
#: None of them failed *because* of a leak. Each failed at a real boundary, with the
#: harness at fault, which is the expensive kind of wrong: it points the reader at the
#: product code. `without_session_mocks()` below is the way out, and the two files that
#: needed it should have used it rather than re-patching by hand.
_PATCHERS: list = []


def _track(patcher):
    """Start a patcher and remember it so the group can be undone."""
    _PATCHERS.append(patcher)
    return patcher.start()


@contextmanager
def without_session_mocks():
    """Temporarily restore the real implementations, then re-apply the mocks.

    For a test that has to exercise something the session mocks stand in for. It is a
    context manager rather than a flag because the alternative — re-patching by hand —
    is what produced the three workarounds above, and each one had to rediscover which
    module held the name being shadowed (`core.safe_query` versus `risk.helpers`, and so
    on). Getting that wrong looks exactly like a product bug.

    ```python
    with without_session_mocks():
        assert await cache.increment("k", ttl=60) == 1
    ```
    """
    for patcher in reversed(_PATCHERS):
        patcher.stop()
    try:
        yield
    finally:
        for patcher in _PATCHERS:
            patcher.start()


# The id `get_current_user` resolves to for every test, and the subject every `auth_headers`
# token is minted for. Exposed because builder strategies are now owned rows: a test that
# plants one has to plant it for this user, or the route correctly reports it as not found.
_TEST_USER_ID = ""


@pytest.fixture(scope="session")
def test_user_id() -> str:
    """The profile id the test client authenticates as."""
    global _TEST_USER_ID
    if not _TEST_USER_ID:
        _apply_test_mocks()
    return _TEST_USER_ID


def _apply_test_mocks():
    global _MOCKS_APPLIED, _SESSION_AUTH, _TEST_USER_ID
    if _MOCKS_APPLIED:
        return _SESSION_AUTH
    _MOCKS_APPLIED = True

    from main import app
    from core.deps import get_current_user
    from core.models import UserProfile
    from core.security import create_access_token

    test_user_id = str(uuid.uuid4())
    _TEST_USER_ID = test_user_id
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
                role="super_admin",
                is_admin=True,
            )
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    app.dependency_overrides[get_current_user] = _override_get_current_user

    # ── Patch capabilities resolver ──
    from core.capabilities import Capabilities, FREE, SUPER_ADMIN

    TEST_CAPS = Capabilities(
        tier="enterprise",
        max_active_strategies=15,
        trailing_sl_allowed=True,
        reentry_squareoff_allowed=True,
        builder_allowed=True,
        custom_strategy_dev_allowed=True,
        backtest_allowed=True,
        backtest_years=5,
        daily_loss_floor=10000.0,
        live_trading_allowed=True,
    )

    async def _mock_resolve_capabilities(user):
        if user.role == "super_admin":
            return SUPER_ADMIN
        if user.subscription_tier == "enterprise":
            return TEST_CAPS
        return FREE

    # Patch core.deps.resolve_capabilities for route-level capability checks
    import core.deps as deps_module
    _track(patch.object(deps_module, "resolve_capabilities", _mock_resolve_capabilities))

    # ── Patch riskguard DB functions ──
    import risk.riskguard as rg
    import application.services.admin_service as admin_svc

    _track(patch.object(rg, "resolve_capabilities_by_id", AsyncMock(return_value=TEST_CAPS)))
    _track(patch.object(admin_svc, "resolve_capabilities_by_id", AsyncMock(return_value=TEST_CAPS)))

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

    _track(patch.object(rg, "async_safe_single", mock_single))
    _track(patch.object(rg, "async_safe_insert", mock_insert))
    _track(patch.object(rg, "async_safe_update", mock_update))

    import risk.rules as risk_rules
    import risk.helpers as risk_helpers
    _track(patch.object(risk_rules, "async_safe_execute", mock_execute))
    _track(patch.object(risk_helpers, "async_safe_execute", mock_execute))

    # ── Mock global kill-switch cache (admin_service uses core.cache) ──
    import core.cache as cache_module

    _kill_switch_store: dict[str, str] = {}

    async def _mock_cache_get(key: str, default=None):
        return _kill_switch_store.get(key, default)

    async def _mock_cache_set(key: str, value: str, ttl=None, *args, **kwargs):
        _kill_switch_store[key] = value

    async def _mock_cache_delete(key: str, *args, **kwargs):
        _kill_switch_store.pop(key, None)

    async def _mock_cache_increment(key: str, ttl: int = 60, *args, **kwargs):
        return 1

    _track(patch.object(cache_module.cache, "get", _mock_cache_get))
    _track(patch.object(cache_module.cache, "set", _mock_cache_set))
    _track(patch.object(cache_module.cache, "delete", _mock_cache_delete))
    _track(patch.object(cache_module.cache, "increment", _mock_cache_increment))

    # ── Patch strategies Supabase ──
    import application.services.strategy_catalog_service as strat_svc

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
    _track(patch.object(strat_svc, "get_supabase", return_value=strat_mock_sb))

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

    _track(patch.object(auth_routes, "get_http_client", _mock_get_http_client))

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


@pytest.fixture(scope="session")
def auth_headers() -> dict:
    global _SESSION_AUTH
    if _SESSION_AUTH is not None:
        return _SESSION_AUTH
    _SESSION_AUTH = _apply_test_mocks()
    return _SESSION_AUTH
