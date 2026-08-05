"""Phase C: wire-level risk analytics payload — curve downsampling + rejection cap.

The persisted ``BacktestResult.risk_analytics`` model stays exact (full timeline,
curves and per-order rejections); ``_payload_risk`` budgets what goes over the
wire the same way ``PayLOAD_MAX_TRADES``/``max_equity_points`` budget trades and
the equity curve.
"""
import pytest

from backtest.models import (
    BacktestConfig,
    BacktestResult,
    BacktestStatus,
    RiskAnalytics,
    RiskRejection,
)
from routes.v1_backtest import (
    PAYLOAD_MAX_REJECTIONS,
    PAYLOAD_MAX_RISK_POINTS,
    _payload_risk,
    _payload_risk_points,
)

TEST_USER_ID = "test-user-risk-payload"


def _big_analytics(n_points=3000, n_rejections=500) -> RiskAnalytics:
    from backtest.models import RiskCurvePoint, RiskTimelinePoint

    timeline = [
        RiskTimelinePoint(
            index=i,
            timestamp=f"2026-01-{(i % 28) + 1:02d}T09:{(i % 60):02d}:00+05:30",
            equity=1000000.0 + i,
            exposure=float(i % 97),
            drawdown_pct=float(i % 5) / 10.0,
            capital_remaining=1000000.0 + i - (i % 97),
            risk_remaining=100000.0 - i,
            status="trading",
        )
        for i in range(n_points)
    ]
    rejections = [
        RiskRejection(
            timestamp=f"2026-01-05T{(i % 60):02d}:00:00+05:30",
            symbol="NIFTY",
            side="BUY",
            quantity=50,
            price=100.0 + (i % 11),
            rule="MAX_TRADES_PER_DAY",
            reason="Daily trade cap reached",
            capital_remaining=999000.0,
            risk_remaining=100000.0,
            drawdown=0.5,
            exposure=5000.0,
        )
        for i in range(n_rejections)
    ]
    ra = RiskAnalytics(
        enabled=True,
        accepted_trades=10,
        rejected_trades=n_rejections,
        halt_count=0,
        rejection_reasons={"MAX_TRADES_PER_DAY": n_rejections},
        timeline=timeline,
        capital_curve=[
            RiskCurvePoint(index=t.index, timestamp=t.timestamp, value=t.capital_remaining)
            for t in timeline
        ],
        exposure_curve=[
            RiskCurvePoint(index=t.index, timestamp=t.timestamp, value=t.exposure)
            for t in timeline
        ],
        rejections=rejections,
    )
    return ra


def _fake_result(ra: RiskAnalytics) -> BacktestResult:
    r = BacktestResult(
        run_id="bt-risk-001",
        status=BacktestStatus.COMPLETED,
        start_equity=1000000.0,
        end_equity=1005000.0,
        total_trades=10,
        net_pnl=5000.0,
        return_pct=0.5,
        win_rate=50.0,
        candles_analyzed=3000,
    )
    r.config = BacktestConfig(
        strategy_type="graph_strategy",
        strategy_id="abc123def456",
        user_id=TEST_USER_ID,
        symbol="NIFTY",
        interval="15m",
        days=60,
    )
    r.risk_analytics = ra
    return r


# ── _payload_risk_points ──


def test_payload_risk_points_downsamples_over_threshold():
    points = [{"index": i, "value": float(i)} for i in range(1 + PAYLOAD_MAX_RISK_POINTS * 2)]
    out = _payload_risk_points(points)
    assert len(out) <= PAYLOAD_MAX_RISK_POINTS
    assert out[0]["index"] == 0
    assert out[-1]["index"] == points[-1]["index"]
    indices = [p["index"] for p in out]
    assert indices == sorted(indices)


def test_payload_risk_points_passthrough_below_threshold():
    points = [{"index": i, "value": float(i)} for i in range(500)]
    out = _payload_risk_points(points)
    assert out == points


# ── _payload_risk ──


def test_payload_risk_off_passthrough_unchanged():
    ra = RiskAnalytics()  # enabled=False
    d = _payload_risk(ra)
    assert d["enabled"] is False
    assert d == ra.model_dump(mode="json")
    assert "rejections_truncated" not in d


def test_payload_risk_caps_rejections_with_flag():
    ra = _big_analytics()
    d = _payload_risk(ra)
    assert len(d["rejections"]) == PAYLOAD_MAX_REJECTIONS
    assert d["rejections_truncated"] is True
    first = d["rejections"][0]
    assert set(first) >= {"timestamp", "symbol", "side", "quantity", "price", "rule", "reason",
                          "capital_remaining", "risk_remaining", "drawdown", "exposure"}
    assert first["rule"] == "MAX_TRADES_PER_DAY"
    assert first["capital_remaining"] == 999000.0


def test_payload_risk_downsampled_wire_shape():
    ra = _big_analytics(n_points=6000, n_rejections=50)
    d = _payload_risk(ra)
    assert d["enabled"] is True
    assert d["accepted_trades"] == 10
    assert d["rejected_trades"] == 50
    assert d["rejection_reasons"]["MAX_TRADES_PER_DAY"] == 50
    for key in ("timeline", "capital_curve", "exposure_curve"):
        assert len(d[key]) <= PAYLOAD_MAX_RISK_POINTS
        # first/last preserved
        assert d[key][0]["index"] == 0
        assert d[key][-1]["index"] == 5999
    # timeline drops the synthetic over-engineered points, curves derived
    assert d["timeline"][0]["equity"] == ra.timeline[0].equity
    assert d["exposure_curve"][0]["value"] == ra.exposure_curve[0].value


# ── route-level: GET /backtests/{run_id} budgets risk analytics ──


@pytest.mark.asyncio
async def test_get_run_budgets_risk_analytics(client, auth_headers, monkeypatch):
    from routes.v1_backtest import backtest_manager

    ra = _big_analytics(n_points=5000, n_rejections=500)
    result = _fake_result(ra)

    async def fake_get(run_id):
        return result

    monkeypatch.setattr(backtest_manager, "get_run", fake_get)
    resp = await client.get("/api/v1/backtests/bt-risk-001", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "bt-risk-001"
    ra_body = body["risk_analytics"]
    assert ra_body["enabled"] is True
    assert len(ra_body["timeline"]) <= PAYLOAD_MAX_RISK_POINTS
    assert len(ra_body["capital_curve"]) <= PAYLOAD_MAX_RISK_POINTS
    assert len(ra_body["exposure_curve"]) <= PAYLOAD_MAX_RISK_POINTS
    assert len(ra_body["rejections"]) == PAYLOAD_MAX_REJECTIONS
    assert ra_body["rejections_truncated"] is True
    assert ra_body["timeline"][0]["equity"] == ra.timeline[0].equity
    assert ra_body["timeline"][-1]["index"] == ra.timeline[-1].index


@pytest.mark.asyncio
async def test_get_run_risk_off_passthrough(client, auth_headers, monkeypatch):
    from routes.v1_backtest import backtest_manager

    result = _fake_result(RiskAnalytics())

    async def fake_get(run_id):
        return result

    monkeypatch.setattr(backtest_manager, "get_run", fake_get)
    resp = await client.get("/api/v1/backtests/bt-risk-off", headers=auth_headers)
    assert resp.status_code == 200
    ra_body = resp.json()["risk_analytics"]
    assert ra_body["enabled"] is False
    assert ra_body["timeline"] == []
    assert ra_body["rejections"] == []