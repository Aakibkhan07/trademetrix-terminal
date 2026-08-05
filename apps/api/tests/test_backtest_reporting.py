"""Phase E: professional reporting — HMAC share tokens, the public read-only
interactive report page, and the institutional PDF export.
"""
import pytest

from backtest.models import (
    BacktestConfig,
    BacktestResult,
    BacktestStatus,
    RiskAnalytics,
    RiskRejection,
)
from backtest.reporting import render_report_html, share_token, verify_share

TEST_USER_ID = "test-user-reporting"


def _result(**kw) -> BacktestResult:
    cfg = BacktestConfig(
        strategy_type="macd_cross",
        strategy_id="abc123def456",
        user_id=TEST_USER_ID,
        symbol="NIFTY",
        exchange="NSE",
        interval="15m",
        days=60,
        risk_enabled=True,
    )
    r = BacktestResult(
        run_id="bt-report-001",
        status=BacktestStatus.COMPLETED,
        config=cfg,
        start_equity=1000000.0,
        end_equity=1005000.0,
        total_trades=2,
        winning_trades=1,
        losing_trades=1,
        win_rate=50.0,
        net_pnl=5000.0,
        profit_factor=1.5,
        return_pct=0.5,
        max_drawdown_pct=3.2,
        sharpe_ratio=1.1,
        sortino_ratio=1.3,
        calmar_ratio=0.9,
        expectancy=2500.0,
        avg_risk_reward_ratio=1.8,
        alpha=2.1,
        beta=0.6,
        benchmark_return_pct=0.2,
        excess_return_pct=0.3,
        candles_analyzed=1034,
        duration_seconds=12.5,
        equity_curve=[
            {"timestamp": "2026-08-01T09:15:00+05:30", "equity": 1000000.0, "drawdown": 0.0, "drawdown_pct": 0.0},
            {"timestamp": "2026-08-01T09:30:00+05:30", "equity": 1005000.0, "drawdown": 0.0, "drawdown_pct": 0.0},
        ],
        trades=[
            {
                "symbol": "NIFTY", "side": "BUY", "entry_price": 24000.0, "exit_price": 24200.0,
                "quantity": 50, "pnl": 5000.0, "rr": 1.8, "entry_reason": "Bullish crossover",
                "exit_reason": "target", "entry_time": "2026-08-01T09:15:00+05:30",
                "exit_time": "2026-08-01T09:30:00+05:30",
            },
            {
                "symbol": "NIFTY", "side": "SELL", "entry_price": 24200.0, "exit_price": 24230.0,
                "quantity": 50, "pnl": -1500.0, "rr": 0.0, "entry_reason": "Bearish crossover",
                "exit_reason": "stop_loss", "entry_time": "2026-08-01T10:00:00+05:30",
                "exit_time": "2026-08-01T10:15:00+05:30",
            },
        ],
    )
    r.monthly_returns = {"2026-07": 0.3, "2026-08": 0.2}
    ra = RiskAnalytics(
        enabled=True,
        accepted_trades=2,
        rejected_trades=3,
        halt_count=0,
        rejection_reasons={"MAX_TRADES_PER_DAY": 3},
        rejections=[
            RiskRejection(
                timestamp="2026-08-01T09:45:00+05:30", symbol="NIFTY", side="BUY",
                quantity=50, price=24100.0, rule="MAX_TRADES_PER_DAY",
                reason="Daily trade cap reached", capital_remaining=999000.0,
                risk_remaining=50000.0, drawdown=0.5, exposure=5000.0,
            )
        ],
    )
    r.risk_analytics = ra
    for k, v in kw.items():
        setattr(r, k, v)
    return r


# ── share tokens ──


def test_share_token_deterministic_and_verify():
    t1 = share_token("run-abc")
    t2 = share_token("run-abc")
    assert t1 == t2
    assert len(t1) == 24
    assert verify_share("run-abc", t1) is True
    assert share_token("run-abc") != share_token("run-abd")


def test_verify_share_rejects_invalid_and_tampered():
    token = share_token("run-abc")
    assert verify_share("run-abc", "garbage") is False
    assert verify_share("run-abc", "") is False
    tampered = ("0" if token[0] != "0" else "1") + token[1:]
    assert verify_share("run-abc", tampered) is False


# ── standalone HTML report ──


def test_render_report_html_embeds_payload_and_escapes_scripts():
    payload = _result().model_dump(mode="json")
    payload["config"]["symbol"] = "</script><script>alert(1)</script>NIFTY"
    html = render_report_html(payload, "2026-08-05 12:00 UTC")
    assert "TradeMetrix" in html
    assert "Executive Summary" in html
    assert "bt-report-001" in html
    assert "</script><script>alert(1)</script>NIFTY" not in html
    assert "\\u003c/script\\u003e" in html or "<\\/script" in html
    assert "2026-08-05 12:00 UTC" in html
    assert html.count("</script>") == 1


def test_render_report_html_empty_result_does_not_crash():
    r = BacktestResult(run_id="bt-empty", status=BacktestStatus.COMPLETED)
    html = render_report_html(r.model_dump(mode="json"), "2026-08-05 12:00 UTC")
    assert "bt-empty" in html
    assert "Insufficient data" in html


# ── institutional PDF ──


def test_export_pdf_institutional_builds():
    from backtest.exports import export_pdf

    pdf = export_pdf(_result())
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 5000
    assert b"/Type /Page" in pdf


def test_export_pdf_handles_empty_result():
    from backtest.exports import export_pdf

    pdf = export_pdf(BacktestResult(run_id="bt-lonely", status=BacktestStatus.COMPLETED))
    assert pdf[:5] == b"%PDF-"


def test_export_pdf_unavailable_reportlab_raises(monkeypatch):
    from backtest import exports

    monkeypatch.setattr(exports, "_REPORTLAB", False)
    with pytest.raises(RuntimeError, match="reportlab"):
        exports.export_pdf(_result())


# ── routes ──


async def _route_result():
    return _result()


@pytest.mark.asyncio
async def test_share_token_route_requires_auth(client):
    resp = await client.get("/api/v1/backtests/bt-report-001/share-token")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_share_token_route_mints_token_and_url(client, auth_headers, monkeypatch):
    from routes.v1_backtest import backtest_manager

    async def fake_get(run_id):
        return _result()

    monkeypatch.setattr(backtest_manager, "get_run", fake_get)
    resp = await client.get("/api/v1/backtests/bt-report-001/share-token", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert verify_share("bt-report-001", body["token"]) is True
    assert "backtests/report/bt-report-001?t=" in body["url"]


@pytest.mark.asyncio
async def test_report_route_403_without_or_bad_token(client, monkeypatch):
    from routes.v1_backtest import backtest_manager

    async def fake_get(run_id):
        return _result()

    monkeypatch.setattr(backtest_manager, "get_run", fake_get)
    assert (await client.get("/api/v1/backtests/report/bt-report-001")).status_code == 403
    assert (await client.get("/api/v1/backtests/report/bt-report-001?t=bad")).status_code == 403


@pytest.mark.asyncio
async def test_report_route_200_with_valid_token(client, monkeypatch):
    from routes.v1_backtest import backtest_manager

    async def fake_get(run_id):
        return _result()

    monkeypatch.setattr(backtest_manager, "get_run", fake_get)
    token = share_token("bt-report-001")
    resp = await client.get(f"/api/v1/backtests/report/bt-report-001?t={token}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "bt-report-001" in resp.text
    assert "Executive Summary" in resp.text
    assert "NIFTY" in resp.text


@pytest.mark.asyncio
async def test_report_route_404_with_valid_token_missing_run(client, monkeypatch):
    from routes.v1_backtest import backtest_manager

    async def fake_get(run_id):
        return None

    monkeypatch.setattr(backtest_manager, "get_run", fake_get)
    token = share_token("bt-report-ghost")
    resp = await client.get(f"/api/v1/backtests/report/bt-report-ghost?t={token}")
    assert resp.status_code == 404
