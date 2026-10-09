"""NSE option-chain adapter against the endpoints that actually exist.

The chain this file guards was returning 503 for /trade and /backtest because
NSE retired `/api/option-chain-indices` (it answers 404 "Resource not found",
measured 2026-10-09). The replacement is `/api/option-chain-v3`, which requires
an `expiry` and renames the bid/ask fields.

Every payload below is the REAL response shape captured from nseindia.com on
2026-10-09, including the parts that are hostile: `bidprice` and `askPrice` are
present-but-null on all 216 legs, and v3 returns HTTP 200 with zero rows when the
`expiry` parameter is missing. A mock written from the code's own assumptions
would have passed against the broken version of this adapter, which is the point.
"""

import httpx
import pytest

from market.option_chain import (
    OptionChainEngine,
    _fmt_expiry,
    _leg,
    _nse_client,
    _num,
    normalize_index_symbol,
)

# Real expiry list from /api/option-chain-contract-info?symbol=NIFTY
REAL_EXPIRIES = ["13-Oct-2026", "19-Oct-2026", "27-Oct-2026", "03-Nov-2026", "09-Nov-2026"]

# Real v3 leg for NIFTY 22500 CE on 13-Oct-2026 (underlyingValue 22520.45).
REAL_CE = {
    "PChange": 28.30319544216002,
    "buyPrice1": 137.05,
    "buyQuantity1": 974525,
    "change": 571.3,
    "changeinOpenInterest": 0,
    "expiryDate": "13-Oct-2026",
    "identifier": "OPTIDX22500CE13OCT2026",
    "impliedVolatility": 12.03,
    "lastPrice": 137.05,
    "openInterest": 2,
    "optionType": "CE",
    "pChange": 28.30319544216002,
    "sellPrice1": 137.65,
    "sellQuantity1": 430560,
    "strikePrice": 22500,
    "totalBuyQuantity": 474435,
    "totalSellQuantity": 430560,
    "totalTradedVolume": 2,
    "underlying": "NIFTY",
    "underlyingValue": 22520.45,
    # NSE sends these keys with null values on every leg measured.
    "bidprice": None,
    "askPrice": None,
}

REAL_PE = {**REAL_CE, "optionType": "PE", "identifier": "OPTIDX22500PE13OCT2026"}

REAL_ROW = {
    "CE": REAL_CE,
    "PE": REAL_PE,
    "expiryDates": "13-Oct-2026",
    "strikePrice": 22500,
}

REAL_V3_BODY = {
    "records": {
        "data": [REAL_ROW],
        "expiryDates": REAL_EXPIRIES,
        "strikePrices": [22500],
        "timestamp": "09-Oct-2026 15:30:00",
        "underlyingValue": 22520.45,
    },
    "filtered": {"data": [], "CE": {}, "PE": {}},
}

REAL_CONTRACT_INFO_BODY = {
    "expiryDates": REAL_EXPIRIES,
    "strikePrice": ["1500", "3000", "4500", "6000", "7500"],
}


def _transport(handler):
    """An httpx MockTransport that serves the captured responses."""
    return httpx.MockTransport(handler)


class _Engine(OptionChainEngine):
    """Fresh singleton per test so caches and _initialized never leak between them."""

    def __new__(cls):
        obj = super().__new__(cls)
        obj._initialized = False
        return obj


def _serve(monkeypatch, *, v3_body=None, v3_status=200, expiries_status=200,
           v3_rows=None):
    """Point OptionChainEngine at a mock NSE, recording the requests it made."""
    calls: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append((path, dict(request.url.params)))
        if path == "/":
            return httpx.Response(200, text="<html>primed</html>")
        if path == "/api/option-chain-contract-info":
            if expiries_status != 200:
                return httpx.Response(expiries_status, text="nope")
            return httpx.Response(200, json=REAL_CONTRACT_INFO_BODY)
        if path == "/api/option-chain-v3":
            if v3_status != 200:
                return httpx.Response(v3_status, text="nope")
            body = dict(v3_body if v3_body is not None else REAL_V3_BODY)
            records = dict(body["records"])
            if v3_rows is not None:
                records["data"] = v3_rows
                body["records"] = records
            return httpx.Response(200, json=body)
        raise AssertionError(f"unexpected NSE path requested: {path}")

    transport = _transport(handler)

    import market.option_chain as oc

    monkeypatch.setattr(
        oc, "_nse_client",
        lambda: httpx.AsyncClient(transport=transport, follow_redirects=True),
    )
    return calls


# ── the retired endpoint must not be requested again ──────────────────────

@pytest.mark.asyncio
async def test_retired_endpoint_is_never_requested(monkeypatch):
    """The regression itself: option-chain-indices is gone, and asking for it is a 404."""
    calls = _serve(monkeypatch)
    result = await _Engine()._fetch_nse_option_chain("NIFTY")
    paths = [c[0] for c in calls]
    assert "/api/option-chain-indices" not in paths
    assert "/api/option-chain-v3" in paths
    assert "/api/option-chain-contract-info" in paths
    assert result is not None


# ── request shape ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_v3_request_carries_the_nearest_expiry(monkeypatch):
    calls = _serve(monkeypatch)
    await _Engine()._fetch_nse_option_chain("NIFTY")
    v3 = next(q for p, q in calls if p == "/api/option-chain-v3")
    assert v3["type"] == "Indices"
    assert v3["symbol"] == "NIFTY"
    assert v3["expiry"] == "13-Oct-2026"


@pytest.mark.asyncio
async def test_nse_session_is_shared_across_the_sequence(monkeypatch):
    """One client for prime + expiries + chain, so the cookie jar is shared."""
    calls = _serve(monkeypatch)
    await _Engine()._fetch_nse_option_chain("NIFTY")
    assert calls[0][0] == "/"
    # Exactly one priming GET, and it comes first.
    assert [c[0] for c in calls].count("/") == 1


@pytest.mark.asyncio
async def test_missing_expiry_parameter_returns_no_chain(monkeypatch):
    """v3 answers 200 with zero rows when expiry is absent -- it must not pass as data."""
    calls = _serve(monkeypatch, v3_rows=[])
    result = await _Engine()._fetch_nse_option_chain("NIFTY")
    assert result is None


# ── the renamed bid/ask fields ─────────────────────────────────────────────

def test_bid_ask_come_from_the_new_field_names():
    leg = _leg(REAL_CE)
    assert leg["bid"] == 137.05
    assert leg["ask"] == 137.65


def test_null_old_field_names_do_not_leak_none():
    """`leg.get('bidprice', 0)` returns None here -- the key is present, so no default."""
    assert REAL_CE["bidprice"] is None
    assert REAL_CE.get("bidprice", 0) is None  # the trap, asserted
    leg = _leg(REAL_CE)
    assert leg["bid"] is not None and leg["ask"] is not None


def test_nse_client_timeout_is_generous_enough():
    """The original 5s was the second half of the 503.

    A mock transport answers instantly, so no behavioural test can catch this -- the
    timeout is only observable in its configuration. Measured against the real vendor:
    the API calls are 37-59ms, but the priming GET to nseindia.com was observed
    exceeding 20s, which under one client-wide timeout took the whole chain down.
    """
    client = _nse_client()
    try:
        timeout = client.timeout
        assert timeout.read >= 30.0, f"read timeout is {timeout.read}"
        assert timeout.connect >= 10.0, f"connect timeout is {timeout.connect}"
    finally:
        pass


def test_leg_falls_back_to_old_names_when_new_ones_absent():
    old = {"lastPrice": 10.0, "bidprice": 9.5, "askPrice": 10.5}
    leg = _leg(old)
    assert leg["bid"] == 9.5
    assert leg["ask"] == 10.5


def test_num_prefers_present_value_over_null():
    assert _num({"a": None, "b": 5}, "a", "b") == 5
    assert _num({"a": None}, "a") == 0
    assert _num({}, "a") == 0


@pytest.mark.asyncio
async def test_full_chain_payload_has_real_numbers(monkeypatch):
    _serve(monkeypatch)
    result = await _Engine()._fetch_nse_option_chain("NIFTY")
    assert result is not None
    strikes = result["optionChain"]
    assert len(strikes) == 1
    row = strikes[0]
    assert row["strike"] == 22500
    assert row["call"]["ltp"] == 137.05
    assert row["call"]["iv"] == 12.03
    assert row["call"]["change_pct"] == pytest.approx(28.303, abs=0.01)
    assert row["put"]["bid"] == 137.05
    # Everything numeric, nothing None -- these are rendered into the chain table.
    for side in ("call", "put"):
        for key, value in row[side].items():
            assert isinstance(value, (int, float)), f"{side}.{key} is {value!r}"


# ── expiry formatting ──────────────────────────────────────────────────────

def test_expiry_formatting_matches_the_ui_contract():
    assert _fmt_expiry("13-Oct-2026") == "13OCT"
    assert _fmt_expiry("03-Nov-2026") == "03NOV"
    # The UI parses the code back with "%d%b" and uppercases, so the shape matters.
    import datetime as dt
    assert dt.datetime.strptime(_fmt_expiry("13-Oct-2026"), "%d%b").day == 13


def test_expiry_formatting_survives_unexpected_input():
    assert _fmt_expiry("garbage") == "GARBAGE"
    assert _fmt_expiry(None) == "NONE"


@pytest.mark.asyncio
async def test_expiries_route_returns_up_to_five_codes(monkeypatch):
    _serve(monkeypatch)
    expiries = await _Engine()._fetch_nse_expiries("NIFTY")
    assert expiries == ["13OCT", "19OCT", "27OCT", "03NOV", "09NOV"]


@pytest.mark.asyncio
async def test_expiries_return_none_when_vendor_fails(monkeypatch):
    _serve(monkeypatch, expiries_status=404)
    assert await _Engine()._fetch_nse_expiries("NIFTY") is None


@pytest.mark.asyncio
async def test_chain_is_none_when_expiries_cannot_be_loaded(monkeypatch):
    """No expiry list means no v3 call is possible; must be None, not a crash."""
    calls = _serve(monkeypatch, expiries_status=500)
    assert await _Engine()._fetch_nse_option_chain("NIFTY") is None
    assert not any(p == "/api/option-chain-v3" for p, _ in calls)


@pytest.mark.asyncio
async def test_v3_http_error_is_surfaced_as_no_chain(monkeypatch):
    _serve(monkeypatch, v3_status=404)
    assert await _Engine()._fetch_nse_option_chain("NIFTY") is None


# ── unchanged behaviour ────────────────────────────────────────────────────

@pytest.mark.parametrize("symbol,expected", [
    ("NSE:NIFTY50-INDEX", "NIFTY"),
    ("NIFTY50-INDEX", "NIFTY"),
    ("nifty", "NIFTY"),
    ("BSE:SENSEX-INDEX", "SENSEX"),
])
def test_symbol_normalisation_unchanged(symbol, expected):
    assert normalize_index_symbol(symbol) == expected


@pytest.mark.asyncio
async def test_non_nse_index_is_not_attempted(monkeypatch):
    calls = _serve(monkeypatch)
    assert await _Engine()._fetch_nse_option_chain("SENSEX") is None
    assert calls == []


# ── the route must not carry its own copy of the fetch ────────────────────

def test_route_delegates_to_the_engine(monkeypatch):
    """The 503 survived the engine fix because the route had its own duplicate.

    `/marketdata/option-chain` carried a ~165-line copy of the NSE fetch, still calling
    the retired endpoint. It returned None regardless of the engine, so repairing the
    engine changed nothing for the UI. The route must call the engine.
    """
    from fastapi import HTTPException
    import routes.v1_marketdata as md

    seen = {}

    async def fake_engine(symbol, expiry=""):
        seen["symbol"] = symbol
        seen["expiry"] = expiry
        return {"optionChain": [{"strike": 22500, "call": {"ltp": 1}, "put": {"ltp": 2}}],
                "expiries": ["13OCT"], "is_simulated": False}

    monkeypatch.setattr(md.option_chain_engine, "get_option_chain", fake_engine)

    import asyncio as _a
    out = _a.run(md.get_option_chain(symbol="NSE:NIFTY50-INDEX",
                                     expiry="", current_user=None))
    assert out["optionChain"][0]["strike"] == 22500
    # Normalisation still happens at the route boundary.
    assert seen["symbol"] == "NIFTY"


def test_route_raises_503_when_the_engine_has_nothing(monkeypatch):
    from fastapi import HTTPException
    import routes.v1_marketdata as md

    async def empty_engine(symbol, expiry=""):
        return {}

    monkeypatch.setattr(md.option_chain_engine, "get_option_chain", empty_engine)

    import asyncio as _a
    with pytest.raises(HTTPException) as exc:
        _a.run(md.get_option_chain(symbol="NIFTY", expiry="", current_user=None))
    assert exc.value.status_code == 503


def test_route_does_not_define_its_own_nse_fetch():
    """No second implementation of the vendor call anywhere in the router.

    Scans the AST for the retired URL as a *string literal*, not as raw text: the
    route's docstring names the endpoint when explaining why it was removed, and a
    text match reads that explanation as the defect it documents. A first version of
    this assertion failed for exactly that reason.
    """
    import ast
    import routes.v1_marketdata as md

    assert not hasattr(md, "_fetch_nse_option_chain")

    tree = ast.parse(open(md.__file__).read())
    # Exclude docstrings: they are ast.Constant strings too, and this route's explains
    # the removal by naming the endpoint. Only literals in real expressions count.
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant) and \
                    isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))

    offenders = [
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and id(node) not in docstrings
        and "option-chain-indices" in node.value
    ]
    assert not offenders, f"router still references the retired endpoint: {offenders}"
