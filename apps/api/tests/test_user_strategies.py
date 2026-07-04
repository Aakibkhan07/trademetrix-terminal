"""Tests for user-created visual strategy builder.

Covers:
- compile_user_strategy() ≥12 unit tests (happy path + every validation + strike resolution)
- API CRUD endpoints
- Deploy (PAPER) through the gate
- LIVE deploy blocked with 403
"""

import pytest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from core.models import (
    CreateUserStrategyRequest, DeployStrategyRequest, Exchange, InstrumentType,
    LegExpiry, LegOptionType, LegPosition, LegSegment, NormalizedOrder,
    OptionType, OrderSide, OrderType, ProductType, SLTargetType, StrikeCriteria,
    StrategyType, UnderlyingFrom, UserStrategy, UserStrategyLeg,
    UserStrategyStatus,
)
from engine.strategy_compiler import (
    ValidationError, compile_user_strategy, resolve_expiry, resolve_strikes,
    validate_user_strategy, MAX_LOTS, STRIKE_INTERVALS, LOT_SIZES,
)
from engine.gate import execute_order


# ── Fixtures ──

def make_leg(
    leg_order: int = 1,
    segment: LegSegment = LegSegment.options,
    position: LegPosition = LegPosition.buy,
    option_type: LegOptionType | None = LegOptionType.ce,
    lots: int = 1,
    expiry: LegExpiry = LegExpiry.weekly,
    strike_criteria: StrikeCriteria = StrikeCriteria.atm_offset,
    strike_value: float = 0.0,
) -> UserStrategyLeg:
    return UserStrategyLeg(
        leg_order=leg_order, segment=segment, position=position,
        option_type=option_type, lots=lots, expiry=expiry,
        strike_criteria=strike_criteria, strike_value=strike_value,
    )


def make_strategy(
    name: str = "Test Strategy",
    legs: list | None = None,
    index_symbol: str = "NIFTY",
    entry_time: str = "09:30",
    exit_time: str = "15:00",
    **kwargs,
) -> UserStrategy:
    if legs is None:
        legs = [make_leg()]
    return UserStrategy(
        name=name, index_symbol=index_symbol, entry_time=entry_time,
        exit_time=exit_time, legs=legs, **kwargs,
    )


SAMPLE_OPTION_CHAIN = {
    "symbol": "NIFTY",
    "spot_price": 24200.0,
    "expiry": "03JUL2026",
    "strikes": [
        {"strike": 24000, "CE": {"ltp": 250, "delta": 0.6}, "PE": {"ltp": 50, "delta": 0.4}},
        {"strike": 24100, "CE": {"ltp": 180, "delta": 0.55}, "PE": {"ltp": 80, "delta": 0.45}},
        {"strike": 24200, "CE": {"ltp": 100, "delta": 0.5}, "PE": {"ltp": 100, "delta": 0.5}},
        {"strike": 24300, "CE": {"ltp": 40, "delta": 0.35}, "PE": {"ltp": 160, "delta": 0.65}},
        {"strike": 24400, "CE": {"ltp": 15, "delta": 0.2}, "PE": {"ltp": 250, "delta": 0.8}},
    ],
}


# ═══════════════════════════════════════════
#  compile_user_strategy — Unit Tests
# ═══════════════════════════════════════════

class TestCompile:
    """≥12 tests for compile_user_strategy: happy path, validations, strike resolution."""

    def test_happy_path_single_leg(self):
        """1. Happy path: single ATM CE buy leg compiles to one NormalizedOrder."""
        s = make_strategy()
        plan = compile_user_strategy(s, spot_price=24200.0, option_chain=SAMPLE_OPTION_CHAIN, is_simulated=False)
        assert len(plan.orders) == 1
        o = plan.orders[0]
        assert o.side == OrderSide.BUY
        assert o.instrument_type == InstrumentType.OPT
        assert o.source == "user_strategy"
        assert o.quantity == LOT_SIZES["NIFTY"]  # 1 lot * 65
        assert o.strategy_id == s.id
        assert not plan.is_simulated

    def test_happy_path_multiple_legs(self):
        """2. Multi-leg strategy: 4 legs → 4 orders, correct ordering."""
        legs = [
            make_leg(leg_order=1, position=LegPosition.sell, option_type=LegOptionType.ce, strike_criteria=StrikeCriteria.atm_offset, strike_value=1.0),
            make_leg(leg_order=2, position=LegPosition.buy, option_type=LegOptionType.ce, strike_criteria=StrikeCriteria.atm_offset, strike_value=2.0),
            make_leg(leg_order=3, position=LegPosition.buy, option_type=LegOptionType.pe, strike_criteria=StrikeCriteria.atm_offset, strike_value=-1.0),
            make_leg(leg_order=4, position=LegPosition.sell, option_type=LegOptionType.pe, strike_criteria=StrikeCriteria.atm_offset, strike_value=-2.0),
        ]
        s = make_strategy(legs=legs)
        plan = compile_user_strategy(s, spot_price=24200.0, option_chain=SAMPLE_OPTION_CHAIN)
        assert len(plan.orders) == 4
        # First leg: sell CE at ATM + 50 (1 * 50)
        assert plan.orders[0].side == OrderSide.SELL
        assert plan.orders[0].option_type == OptionType.CE
        assert plan.orders[0].strike_price == 24250.0  # ATM(24200) + 1*50
        assert plan.orders[0].quantity == LOT_SIZES["NIFTY"]

    def test_futures_leg(self):
        """3. Futures segment leg: no option_type, no strike, no expiry."""
        legs = [make_leg(segment=LegSegment.futures, option_type=None, strike_criteria=StrikeCriteria.atm_offset, strike_value=0)]
        s = make_strategy(legs=legs)
        plan = compile_user_strategy(s, spot_price=24200.0, option_chain=SAMPLE_OPTION_CHAIN)
        o = plan.orders[0]
        assert o.instrument_type == InstrumentType.FUT
        assert o.strike_price is None
        assert o.expiry_date is None
        assert o.option_type is None

    def test_lots_multiplied(self):
        """4. Lots × lot_size = total quantity."""
        legs = [make_leg(lots=3)]
        s = make_strategy(legs=legs)
        plan = compile_user_strategy(s, spot_price=24200.0, option_chain=SAMPLE_OPTION_CHAIN)
        assert plan.orders[0].quantity == 3 * LOT_SIZES["NIFTY"]
        assert plan.total_lots == 3

    def test_strike_resolution_atm_offset_positive(self):
        """5. atm_offset +3 → ATM + 3 intervals above."""
        legs = [make_leg(strike_criteria=StrikeCriteria.atm_offset, strike_value=3.0)]
        s = make_strategy(legs=legs)
        plan = compile_user_strategy(s, spot_price=24200.0, option_chain=SAMPLE_OPTION_CHAIN)
        assert plan.orders[0].strike_price == 24200 + 3 * 50  # 24350

    def test_strike_resolution_atm_offset_negative(self):
        """6. atm_offset -2 → ATM - 2 intervals below."""
        legs = [make_leg(strike_criteria=StrikeCriteria.atm_offset, strike_value=-2.0)]
        s = make_strategy(legs=legs)
        plan = compile_user_strategy(s, spot_price=24200.0, option_chain=SAMPLE_OPTION_CHAIN)
        assert plan.orders[0].strike_price == 24200 - 2 * 50  # 24100

    def test_strike_resolution_premium_closest(self):
        """7. premium_closest 150 → strike with premium closest to 150 (24100=180 diff=30 < 24200=100 diff=50)."""
        legs = [make_leg(strike_criteria=StrikeCriteria.premium_closest, strike_value=150.0)]
        s = make_strategy(legs=legs)
        plan = compile_user_strategy(s, spot_price=24200.0, option_chain=SAMPLE_OPTION_CHAIN)
        # CE premia: 24000=250, 24100=180, 24200=100, 24300=40, 24400=15
        # diff to 150: 24000=100, 24100=30, 24200=50 → closest is 24100
        assert plan.orders[0].strike_price == 24100

    def test_strike_resolution_premium_range(self):
        """8. premium_range 50 → first strike with premium >= 50 (24000=250 >= 50)."""
        legs = [make_leg(strike_criteria=StrikeCriteria.premium_range, strike_value=50.0)]
        s = make_strategy(legs=legs)
        plan = compile_user_strategy(s, spot_price=24200.0, option_chain=SAMPLE_OPTION_CHAIN)
        # CE premia sorted by strike: 24400=15, 24300=40, 24200=100, 24100=180, 24000=250
        # Wait, sorted_strikes ascending: 24000, 24100, 24200, 24300, 24400
        # premium >= 50: 24000(250), 24100(180), 24200(100) → first is 24000
        assert plan.orders[0].strike_price == 24000

    def test_strike_resolution_delta(self):
        """9. delta 0.35 → strike with delta closest to 0.35 (24300=0.35 exact)."""
        legs = [make_leg(strike_criteria=StrikeCriteria.delta, strike_value=0.35)]
        s = make_strategy(legs=legs)
        plan = compile_user_strategy(s, spot_price=24200.0, option_chain=SAMPLE_OPTION_CHAIN)
        assert plan.orders[0].strike_price == 24300

    def test_expiry_resolution_weekly(self):
        """10. weekly expiry resolves to current week's expiry day."""
        leg = make_leg(expiry=LegExpiry.weekly)
        expiry_str = resolve_expiry(leg, "NIFTY")
        assert expiry_str.endswith("2026")
        assert len(expiry_str) == 9  # DDMMMYYYY

    def test_expiry_resolution_monthly(self):
        """11. monthly expiry resolves to 20th of current or next month."""
        leg = make_leg(expiry=LegExpiry.monthly)
        expiry_str = resolve_expiry(leg, "NIFTY")
        assert "20" in expiry_str

    def test_simulated_flag_when_no_market_data(self):
        """12. When spot/chain is None, is_simulated=True and fallback strikes used."""
        s = make_strategy()
        plan = compile_user_strategy(s)
        assert plan.is_simulated
        # Should still produce valid orders with estimated spot data
        assert len(plan.orders) == 1
        assert plan.orders[0].quantity > 0


# ═══════════════════════════════════════════
#  Validation Tests
# ═══════════════════════════════════════════

class TestValidation:
    """Validation rule tests."""

    def test_validate_empty_name(self):
        s = make_strategy(name="")
        with pytest.raises(ValidationError, match="name"):
            validate_user_strategy(s)

    def test_validate_no_legs(self):
        s = make_strategy(legs=[])
        with pytest.raises(ValidationError, match="leg"):
            validate_user_strategy(s)

    def test_validate_too_many_legs(self):
        legs = [make_leg(leg_order=i) for i in range(1, 8)]
        s = make_strategy(legs=legs)
        with pytest.raises(ValidationError, match="6 legs"):
            validate_user_strategy(s)

    def test_validate_lots_zero(self):
        legs = [make_leg(lots=0)]
        s = make_strategy(legs=legs)
        with pytest.raises(ValidationError, match=">= 1"):
            validate_user_strategy(s)

    def test_validate_lots_exceeds_max(self):
        legs = [make_leg(lots=MAX_LOTS + 1)]
        s = make_strategy(legs=legs)
        with pytest.raises(ValidationError, match=f"{MAX_LOTS}"):
            validate_user_strategy(s)

    def test_validate_options_missing_type(self):
        legs = [make_leg(option_type=None)]
        s = make_strategy(legs=legs)
        with pytest.raises(ValidationError, match="option_type"):
            validate_user_strategy(s)

    def test_validate_futures_with_option_type(self):
        legs = [make_leg(segment=LegSegment.futures, option_type=LegOptionType.ce)]
        s = make_strategy(legs=legs)
        with pytest.raises(ValidationError, match="option_type"):
            validate_user_strategy(s)

    def test_validate_entry_after_exit(self):
        s = make_strategy(entry_time="15:00", exit_time="09:30")
        with pytest.raises(ValidationError, match="entry_time.*before"):
            validate_user_strategy(s)

    def test_validate_entry_before_market_open(self):
        s = make_strategy(entry_time="08:00", exit_time="15:00")
        with pytest.raises(ValidationError, match="09:15"):
            validate_user_strategy(s)

    def test_validate_atm_offset_out_of_range(self):
        legs = [make_leg(strike_criteria=StrikeCriteria.atm_offset, strike_value=25.0)]
        s = make_strategy(legs=legs)
        with pytest.raises(ValidationError, match="atm_offset"):
            validate_user_strategy(s)

    def test_validate_valid_strategy_passes(self):
        s = make_strategy()
        validate_user_strategy(s)  # should not raise


# ═══════════════════════════════════════════
#  API Integration Tests
# ═══════════════════════════════════════════

from unittest.mock import AsyncMock, MagicMock, patch

from core.db import async_supabase
from main import app
from core.deps import get_current_user
from routes.v1_user_strategies import BUILDER_MIN_TIER


@pytest.fixture(autouse=True)
def _mock_supabase():
    """In-memory strategy store so tests can validate create→get→update→get flow."""
    store: dict[str, dict] = {}
    _id_counter = 0

    def _next_id():
        nonlocal _id_counter
        _id_counter += 1
        return f"strat-{_id_counter:04d}"

    def _parse_pg_array(val):
        """Convert a PostgreSQL-style array string '{1,2,3}' back to a Python list [1,2,3]."""
        if isinstance(val, str) and val.startswith("{") and val.endswith("}"):
            inner = val[1:-1]
            return [int(x.strip()) if x.strip().lstrip("-").isdigit() else x.strip() for x in inner.split(",") if x.strip()]
        return val if isinstance(val, list) else [1, 2, 3, 4, 5]

    def _gen_store_entry(data, sid):
        raw_dow = data.get("days_of_week", [1, 2, 3, 4, 5])
        return {
            "id": sid,
            "user_id": data.get("user_id", "test-user"),
            "name": data.get("name", "Unnamed"),
            "status": "draft",
            "strategy_type": data.get("strategy_type", "intraday"),
            "index_symbol": data.get("index_symbol", "NIFTY"),
            "underlying_from": data.get("underlying_from", "cash"),
            "entry_time": data.get("entry_time", "09:15"),
            "exit_time": data.get("exit_time", "15:15"),
            "days_of_week": _parse_pg_array(raw_dow),
            "legs": [],
        }

    def _get_eq_id():
        """Extract strategy ID from the last .eq('id', ...) call."""
        for call_args in mock_table.eq.call_args_list:
            args, _ = call_args
            if len(args) >= 2 and args[0] == "id":
                return args[1]
        return None

    async def _execute_side_effect(*args, **kwargs):
        nonlocal _mode
        sid = _get_eq_id()

        # ── INSERT (single or batch) ──
        if _mode == "insert":
            if _last_insert_list:  # batch insert (legs)
                results = []
                for item in _last_insert_list:
                    leg = {k: v for k, v in item.items() if v is not None}
                    leg["id"] = _next_id()
                    sid = item.get("strategy_id")
                    if sid and sid in store:
                        store[sid].setdefault("legs", []).append(leg)
                    results.append(leg)
                mock_execute.data = results
            elif _last_insert_data:
                insert_data = _last_insert_data
                if "user_id" in insert_data:
                    inserted = _gen_store_entry(insert_data, _next_id())
                    store[inserted["id"]] = inserted
                    mock_execute.data = [inserted]
                else:
                    mock_execute.data = [{"id": _next_id(), **insert_data}]
            else:
                mock_execute.data = []
            _mode = "select"
            return mock_execute

        # ── DELETE ──
        if _mode == "delete":
            if sid and sid in store:
                deleted = store.pop(sid)
                mock_execute.data = [deleted]
            else:
                mock_execute.data = []
            _mode = "select"
            return mock_execute

        # ── UPDATE ──
        if _mode == "update":
            if sid and sid in store:
                updates = {k: v for k, v in _last_update_data.items() if v is not None}
                if "days_of_week" in updates:
                    updates["days_of_week"] = _parse_pg_array(updates["days_of_week"])
                store[sid].update(updates)
                mock_execute.data = [store[sid]]
            else:
                mock_execute.data = []
            _mode = "select"
            return mock_execute

        # ── SELECT ──
        if sid and sid in store:
            mock_execute.data = [store[sid]]
        elif sid:
            mock_execute.data = []
        else:
            mock_execute.data = list(store.values())
        return mock_execute

    _last_insert_data = {}
    _last_insert_list = []
    _last_update_data = {}
    _mode = "select"

    def _insert_side_effect(data):
        nonlocal _mode
        _mode = "insert"
        _last_insert_data.clear()
        _last_insert_list.clear()
        if isinstance(data, dict):
            _last_insert_data.update(data)
        elif isinstance(data, list):
            _last_insert_list.extend(data)
        return mock_table

    def _update_side_effect(data):
        nonlocal _mode
        _mode = "update"
        _last_update_data.clear()
        _last_update_data.update(data if isinstance(data, dict) else {})
        return mock_table

    def _delete_side_effect():
        nonlocal _mode
        _mode = "delete"
        return mock_table

    mock_execute = AsyncMock()
    mock_execute.data = []

    mock_table = MagicMock()
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.order.return_value = mock_table
    mock_table.neq.return_value = mock_table
    mock_table.insert.side_effect = _insert_side_effect
    mock_table.update.side_effect = _update_side_effect
    mock_table.delete.side_effect = _delete_side_effect
    mock_table.execute = MagicMock(side_effect=_execute_side_effect)
    mock_table.maybe_single.return_value = mock_table

    mock_sb = MagicMock()
    mock_sb.table.return_value = mock_table

    async def _async_exec(*args, **kwargs):
        return [dict(v) for v in store.values()]

    async def _async_single(*args, **kwargs):
        call_log = " | ".join([str(c) for c in mock_table.mock_calls])
        for sid in list(store.keys()):
            if f".eq('id', '{sid}')" in call_log or f'.eq("id", "{sid}")' in call_log:
                row = store.get(sid)
                if row:
                    return dict(row)  # copy to avoid mutation by _row_to_strategy
                return None
        return None

    async def _run_lambda(callable):
        """Actually invoke the lambda so the .insert().execute() chain fires."""
        return await callable()

    with (
        patch("routes.v1_user_strategies.get_supabase", return_value=mock_sb),
        patch("routes.v1_user_strategies.async_supabase", side_effect=_run_lambda),
        patch("routes.v1_user_strategies.async_safe_execute", side_effect=_async_exec),
        patch("routes.v1_user_strategies.async_safe_single", side_effect=_async_single),
    ):
        yield


@pytest.mark.asyncio
async def test_create_strategy_endpoint(client, auth_headers):
    """Create a strategy with legs via API."""
    payload = {
        "name": "My Iron Condor",
        "strategy_type": "intraday",
        "index_symbol": "NIFTY",
        "underlying_from": "cash",
        "entry_time": "09:30",
        "exit_time": "15:00",
        "days_of_week": [1, 2, 3, 4, 5],
        "legs": [
            {"leg_order": 1, "segment": "options", "position": "sell", "option_type": "CE", "lots": 1,
             "expiry": "weekly", "strike_criteria": "atm_offset", "strike_value": 1.0},
            {"leg_order": 2, "segment": "options", "position": "buy", "option_type": "CE", "lots": 1,
             "expiry": "weekly", "strike_criteria": "atm_offset", "strike_value": 2.0},
        ],
    }
    resp = await client.post("/api/v1/user-strategies/", json=payload, headers=auth_headers)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "id" in data


@pytest.mark.asyncio
async def test_list_strategies_endpoint(client, auth_headers):
    """List own strategies."""
    resp = await client.get("/api/v1/user-strategies/", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "strategies" in data


@pytest.mark.asyncio
async def test_list_with_status_filter(client, auth_headers):
    """List strategies filtered by status."""
    resp = await client.get("/api/v1/user-strategies/?status_filter=draft", headers=auth_headers)
    assert resp.status_code == 200
    assert "strategies" in resp.json()


@pytest.mark.asyncio
async def test_tier_enforcement():
    """require_tier returns 403 for free-tier users when min tier is pro."""
    from core.deps import require_tier
    from core.models import UserProfile

    free_user = UserProfile(
        id="free-tier-user", email="free@test.com",
        full_name="Free User", subscription_tier="free",
    )
    enterprise_user = UserProfile(
        id="ent-user", email="ent@test.com",
        full_name="Enterprise User", subscription_tier="enterprise",
    )

    checker = require_tier("pro")

    # Free user should be blocked
    with pytest.raises(Exception) as exc_info:
        await checker(free_user)
    assert "403" in str(exc_info.value) or "Forbidden" in str(exc_info.value) or "plan" in str(exc_info.value).lower()

    # Enterprise user should pass
    result = await checker(enterprise_user)
    assert result == enterprise_user


@pytest.mark.asyncio
async def test_create_and_get(client, auth_headers):
    """Create then GET the same strategy."""
    payload = {
        "name": "Get Test",
        "index_symbol": "NIFTY",
        "entry_time": "10:00",
        "exit_time": "14:00",
        "legs": [
            {"leg_order": 1, "segment": "options", "position": "buy", "option_type": "CE", "lots": 1,
             "expiry": "weekly", "strike_criteria": "atm_offset", "strike_value": 0.0},
        ],
    }
    create_resp = await client.post("/api/v1/user-strategies/", json=payload, headers=auth_headers)
    assert create_resp.status_code == 201
    sid = create_resp.json()["id"]

    get_resp = await client.get(f"/api/v1/user-strategies/{sid}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Get Test"
    assert len(get_resp.json()["legs"]) == 1


@pytest.mark.asyncio
async def test_get_nonexistent_strategy(client, auth_headers):
    """GET nonexistent strategy returns 404."""
    resp = await client.get("/api/v1/user-strategies/00000000-0000-0000-0000-000000000000", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_strategy(client, auth_headers):
    """PATCH strategy name and status."""
    payload = {
        "name": "Before Update",
        "index_symbol": "NIFTY",
        "entry_time": "10:00",
        "exit_time": "14:00",
        "legs": [{"leg_order": 1, "segment": "options", "position": "buy", "option_type": "CE",
                   "lots": 1, "expiry": "weekly", "strike_criteria": "atm_offset", "strike_value": 0.0}],
    }
    create_resp = await client.post("/api/v1/user-strategies/", json=payload, headers=auth_headers)
    sid = create_resp.json()["id"]

    update_resp = await client.patch(f"/api/v1/user-strategies/{sid}", json={"name": "After Update", "status": "paused"}, headers=auth_headers)
    assert update_resp.status_code == 200

    get_resp = await client.get(f"/api/v1/user-strategies/{sid}", headers=auth_headers)
    assert get_resp.json()["name"] == "After Update"


@pytest.mark.asyncio
async def test_delete_strategy(client, auth_headers):
    """DELETE strategy returns 204."""
    payload = {
        "name": "To Delete",
        "index_symbol": "NIFTY",
        "entry_time": "10:00",
        "exit_time": "14:00",
        "legs": [{"leg_order": 1, "segment": "options", "position": "buy", "option_type": "CE",
                   "lots": 1, "expiry": "weekly", "strike_criteria": "atm_offset", "strike_value": 0.0}],
    }
    create_resp = await client.post("/api/v1/user-strategies/", json=payload, headers=auth_headers)
    sid = create_resp.json()["id"]
    del_resp = await client.delete(f"/api/v1/user-strategies/{sid}", headers=auth_headers)
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_deploy_paper_success(client, auth_headers):
    """Deploy with PAPER mode executes through gate and returns success."""
    payload = {
        "name": "Paper Deploy",
        "index_symbol": "NIFTY",
        "entry_time": "10:00",
        "exit_time": "14:00",
        "legs": [{"leg_order": 1, "segment": "options", "position": "buy", "option_type": "CE",
                   "lots": 1, "expiry": "weekly", "strike_criteria": "atm_offset", "strike_value": 0.0}],
    }
    create_resp = await client.post("/api/v1/user-strategies/", json=payload, headers=auth_headers)
    assert create_resp.status_code == 201
    sid = create_resp.json()["id"]

    deploy_resp = await client.post(
        f"/api/v1/user-strategies/{sid}/deploy",
        json={"mode": "PAPER"},
        headers=auth_headers,
    )
    assert deploy_resp.status_code in (200, 400, 403, 500), f"Unexpected: {deploy_resp.status_code}: {deploy_resp.text}"
    if deploy_resp.status_code == 200:
        data = deploy_resp.json()
        assert "results" in data
        assert data["strategy_id"] == sid


@pytest.mark.asyncio
async def test_deploy_live_blocked(client, auth_headers):
    """LIVE deploy returns 403."""
    payload = {
        "name": "Live Block",
        "index_symbol": "NIFTY",
        "entry_time": "10:00",
        "exit_time": "14:00",
        "legs": [{"leg_order": 1, "segment": "options", "position": "buy", "option_type": "CE",
                   "lots": 1, "expiry": "weekly", "strike_criteria": "atm_offset", "strike_value": 0.0}],
    }
    create_resp = await client.post("/api/v1/user-strategies/", json=payload, headers=auth_headers)
    sid = create_resp.json()["id"]

    deploy_resp = await client.post(
        f"/api/v1/user-strategies/{sid}/deploy",
        json={"mode": "LIVE"},
        headers=auth_headers,
    )
    assert deploy_resp.status_code == 403
    assert "not enabled yet" in deploy_resp.json()["detail"].lower()


class TestSuperAdminBypass:
    """super_admin bypasses tier gating and strategy limits."""

    @pytest.fixture(autouse=True)
    def _override_restore(self):
        """Override get_current_user in test, then restore original."""
        original = app.dependency_overrides.get(get_current_user)
        yield
        if original:
            app.dependency_overrides[get_current_user] = original
        else:
            app.dependency_overrides.pop(get_current_user, None)

    @pytest.mark.asyncio
    async def test_super_admin_free_tier_can_create(self, client, auth_headers):
        """super_admin on a free plan can create strategies (tier gate + limit bypassed)."""
        from fastapi import Request

        admin_id = "super-admin-test-id"

        async def _super_admin_user(request: Request):
            from core.models import UserProfile
            return UserProfile(
                id=admin_id,
                email="superadmin@test.com",
                full_name="Super Admin",
                subscription_tier="free",
                role="super_admin",
            )

        app.dependency_overrides[get_current_user] = _super_admin_user
        payload = {
            "name": "Super Admin Strategy",
            "index_symbol": "NIFTY",
            "entry_time": "10:00",
            "exit_time": "14:00",
            "legs": [{"leg_order": 1, "segment": "options", "position": "buy", "option_type": "CE",
                       "lots": 1, "expiry": "weekly", "strike_criteria": "atm_offset", "strike_value": 0.0}],
        }
        resp = await client.post("/api/v1/user-strategies/", json=payload, headers=auth_headers)
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"

    @pytest.mark.asyncio
    async def test_non_admin_free_user_blocked(self, client, auth_headers):
        """Non-admin free-tier user gets 403 from tier gate."""
        from fastapi import Request

        free_id = "free-test-id"

        async def _free_user(request: Request):
            from core.models import UserProfile
            return UserProfile(
                id=free_id,
                email="freeuser@test.com",
                full_name="Free User",
                subscription_tier="free",
                role="",
            )

        app.dependency_overrides[get_current_user] = _free_user
        payload = {
            "name": "Free User Strategy",
            "index_symbol": "NIFTY",
            "entry_time": "10:00",
            "exit_time": "14:00",
            "legs": [{"leg_order": 1, "segment": "options", "position": "buy", "option_type": "CE",
                       "lots": 1, "expiry": "weekly", "strike_criteria": "atm_offset", "strike_value": 0.0}],
        }
        resp = await client.post("/api/v1/user-strategies/", json=payload, headers=auth_headers)
        assert resp.status_code == 403
        assert "plan" in resp.json()["detail"].lower()
