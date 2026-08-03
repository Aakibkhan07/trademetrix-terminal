"""Live certification runner tests (SDK v2 Phase 4)."""
import asyncio

import pytest

from brokers.sdk.errors import UnsupportedFeatureError
from brokers.sdk.live_cert import (
    LIVE_STEPS,
    LiveCertResult,
    default_driver,
    run_live_certification,
    write_report,
)


class HealthyAdapter:
    broker_name = "fakebroker"

    async def connect(self, credentials):
        return {"ok": True}

    async def disconnect(self):
        return None

    async def refresh_token(self, credentials):
        return {"ok": True}

    async def get_quotes(self, symbols):
        return [{"ltp": 100}]

    async def get_historical_data(self, symbol, interval, **kwargs):
        return {"candles": [1, 2, 3]}

    async def get_option_chain(self, symbol, **kwargs):
        return {"option_chain": []}

    async def get_positions(self):
        return []

    async def get_holdings(self):
        return []

    async def get_funds(self):
        return {}

    async def place_order(self, **kwargs):
        return {"broker_order_id": "o1", "status": "FILLED"}

    async def modify_order(self, **kwargs):
        return {"broker_order_id": "o1", "status": "FILLED"}

    async def cancel_order(self, **kwargs):
        return {"broker_order_id": "o1", "status": "CANCELLED"}

    def subscribe_market_data(self, symbols, on_tick):
        return asyncio.sleep(0)


class BrokenAdapter(HealthyAdapter):
    broker_name = "brokenbroker"

    async def connect(self):
        raise ConnectionError("net down")

    async def get_quotes(self, symbols):
        raise ConnectionError("net down")


class ExpiredTokenAdapter(HealthyAdapter):
    broker_name = "expiredbroker"

    async def refresh_token(self, credentials):
        raise RuntimeError("expired token")


@pytest.mark.asyncio
async def test_live_cert_healthy_passes_non_order_steps():
    result = await run_live_certification(HealthyAdapter())
    assert result.passed is True
    assert result.to_dict()["result"] == "LIVE_CERTIFIED"
    order_steps = {s["check"] for s in result.steps.values() if s.get("skipped")}
    assert order_steps == {"place_order", "modify_order", "cancel_order"}


@pytest.mark.asyncio
async def test_live_cert_broken_adapter_fails():
    result = await run_live_certification(BrokenAdapter())
    assert result.passed is False
    assert result.to_dict()["result"] == "LIVE_NOT_CERTIFIED"
    login = result.steps["login"]
    assert login["passed"] is False


@pytest.mark.asyncio
async def test_live_cert_token_expiry_failure_invalidates():
    result = await run_live_certification(ExpiredTokenAdapter())
    assert result.passed is False
    assert result.steps["token_expiry"]["passed"] is False


@pytest.mark.asyncio
async def test_live_cert_order_steps_opt_in():
    result = await run_live_certification(HealthyAdapter(), allow_orders=True)
    assert all(s["skipped"] is False for s in result.steps.values())
    assert result.passed is True


@pytest.mark.asyncio
async def test_live_cert_timeout_recorded():
    class SlowAdapter(HealthyAdapter):
        async def get_funds(self):
            await asyncio.sleep(10)

    result = await run_live_certification(SlowAdapter(), timeout=0.05)
    assert result.steps["funds"]["error"].startswith("timeout")


def test_live_cert_result_serialisable(tmp_path):
    result = LiveCertResult(broker="fakebroker")
    result.add("login", True, detail="ok")
    result.add("place_order", False, detail="skipped", skipped=True)
    d = result.to_dict()
    assert d["result"] == "LIVE_CERTIFIED"
    write_report(result, str(tmp_path / "cert.json"))
    assert (tmp_path / "cert.json").exists()
    assert (tmp_path / "cert.md").exists()


def test_live_cert_required_steps_present():
    for step in (
        "login",
        "token_refresh",
        "quotes",
        "history",
        "option_chain",
        "websocket",
        "positions",
        "holdings",
        "funds",
        "disconnect",
        "reconnect",
        "token_expiry",
        "circuit_recovery",
    ):
        assert step in LIVE_STEPS, step


@pytest.mark.asyncio
async def test_live_cert_default_driver_covers_all_steps():
    adapter = HealthyAdapter()
    for step in LIVE_STEPS:
        driver = default_driver(adapter, step)
        assert driver is not None, step


def test_live_cert_markdown_report(tmp_path):
    result = LiveCertResult(broker="fakebroker")
    result.add("login", True, detail="ok")
    result.add("quotes", False, error="timeout >20s")
    write_report(result, str(tmp_path / "cert.json"))
    md = (tmp_path / "cert.md").read_text()
    assert "Live Certification" in md
    assert "PASS" in md
    assert "FAIL" in md


@pytest.mark.asyncio
async def test_live_cert_capability_absent_is_skipped_not_fail():
    class LimitedAdapter(HealthyAdapter):
        broker_name = "limitedbroker"

        async def get_option_chain(self, symbol, **kwargs):
            raise UnsupportedFeatureError("get_option_chain", broker=self.broker_name)

        async def refresh_token(self, credentials):
            raise UnsupportedFeatureError("refresh_token", broker=self.broker_name)

    result = await run_live_certification(LimitedAdapter())
    # capability-absent capability is skipped (the cert still passes)
    assert result.passed is True
    skipped = {s["check"] for s in result.steps.values() if s.get("skipped")}
    assert {"option_chain", "token_refresh", "token_expiry"} <= skipped
    assert result.steps["option_chain"]["skipped"] is True


@pytest.mark.asyncio
async def test_live_help_citation_recipe_attributes(tmp_path):
    """CLI usage recipe referenced by docs must resolve to real names."""
    from brokers.live_cert import _load_adapter, _resolve_credentials

    assert callable(_load_adapter)
    assert callable(_resolve_credentials)