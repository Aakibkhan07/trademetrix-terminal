import pytest

from backtest.models import BacktestConfig, BacktestResult, BacktestStatus, TradeRecord

TEST_USER_ID = "test-user-5-6"


def _fake_result(run_id="bt-5-6-001"):
    r = BacktestResult(
        run_id=run_id,
        status=BacktestStatus.COMPLETED,
        start_equity=100000.0,
        end_equity=103500.0,
        net_pnl=3500.0,
        return_pct=3.5,
        total_trades=20,
        win_rate=55.0,
        profit_factor=1.6,
        max_drawdown_pct=4.2,
        sharpe_ratio=1.3,
        sortino_ratio=1.7,
        calmar_ratio=0.9,
        expectancy=175.0,
        expectancy_per_r=0.35,
        avg_risk_reward_ratio=1.4,
        median_risk_reward_ratio=1.2,
        alpha=2.1,
        beta=0.9,
        benchmark_return_pct=2.0,
        excess_return_pct=1.5,
        candles_analyzed=400,
    )
    r.config = BacktestConfig(
        strategy_type="graph_strategy",
        strategy_params={"_dsl": {"name": "x"}},
        strategy_id="abc123def456",
        user_id=TEST_USER_ID,
        symbol="NIFTY",
        interval="15m",
        days=60,
    )
    r.trades = [TradeRecord(
        symbol="NIFTY", side="BUY", entry_price=100, exit_price=101,
        quantity=50, pnl=50.0,
        entry_time="2026-01-05T10:00:00+00:00",
        exit_time="2026-01-05T10:15:00+00:00",
    ) for _ in range(20)]
    r.equity_curve = [{"index": i, "equity": 100000.0 + i * 8.75} for i in range(401)]
    return r


@pytest.mark.asyncio
async def test_run_v3_with_builder_strategy(monkeypatch, client, auth_headers):
    from builder.manager import builder_manager
    from builder.models import StrategyDSL, ValidationResult
    from routes.v1_backtest import backtest_manager

    dsl = StrategyDSL(name="v3-test", description="", settings={})

    async def fake_get(sid):
        assert sid == "abc123def456"
        return dsl

    def fake_compile(d):
        return object(), ValidationResult(valid=True, issues=[])

    async def fake_run(config):
        assert config.strategy_type == "graph_strategy"
        assert config.strategy_params == {"_dsl": dsl.model_dump(mode="json")}
        assert config.user_id
        result = _fake_result(run_id="bt-5-6-v3")
        result.config = config
        return result

    monkeypatch.setattr(builder_manager, "get", fake_get)
    monkeypatch.setattr("builder.compiler.compile_dsl", fake_compile)
    monkeypatch.setattr(backtest_manager, "run", fake_run)

    resp = await client.post(
        "/api/v1/backtests/run-v3",
        json={"strategy_id": "abc123def456", "symbol": "NIFTY", "days": 30},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["run_id"] == "bt-5-6-v3"
    assert body["strategy_id"] == "abc123def456"
    assert body["summary"]["expectancy"] == 175.0
    assert body["summary"]["alpha"] == 2.1
    assert body["summary"]["win_rate"] == 55.0
    assert len(body["trades"]) == 20
    assert len(body["equity_curve"]) == 401


@pytest.mark.asyncio
async def test_run_v3_missing_strategy_404(monkeypatch, client, auth_headers):
    from builder.manager import builder_manager

    async def fake_get(sid):
        return None

    monkeypatch.setattr(builder_manager, "get", fake_get)

    resp = await client.post(
        "/api/v1/backtests/run-v3",
        json={"strategy_id": "nope"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_run_v3_invalid_dsl_400(monkeypatch, client, auth_headers):
    from builder.manager import builder_manager
    from builder.models import StrategyDSL, ValidationIssue, ValidationResult

    async def fake_get(sid):
        return StrategyDSL(name="bad", description="", settings={})

    def fake_compile(d):
        return None, ValidationResult(valid=False, issues=[
            ValidationIssue(severity="error", message="missing indicator"),
        ])

    monkeypatch.setattr(builder_manager, "get", fake_get)
    monkeypatch.setattr("builder.compiler.compile_dsl", fake_compile)

    resp = await client.post(
        "/api/v1/backtests/run-v3",
        json={"strategy_id": "abc123def456"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "missing indicator" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_compare_runs(monkeypatch, client, auth_headers):
    from routes.v1_backtest import backtest_manager

    async def fake_get(run_id):
        if run_id == "bt-ghost":
            return None
        return _fake_result(run_id=run_id)

    monkeypatch.setattr(backtest_manager, "get_run", fake_get)

    resp = await client.post(
        "/api/v1/backtests/compare",
        json={"run_ids": ["bt-1", "bt-2", "bt-ghost"]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    comparison = resp.json()["comparison"]
    assert set(comparison.keys()) == {"bt-1", "bt-2"}
    assert comparison["bt-1"]["net_pnl"] == 3500.0
    assert comparison["bt-1"]["alpha"] == 2.1


@pytest.mark.asyncio
async def test_compare_requires_run_ids(client, auth_headers):
    resp = await client.post(
        "/api/v1/backtests/compare",
        json={},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_export_json_and_csv(monkeypatch, client, auth_headers):
    from routes.v1_backtest import backtest_manager

    async def fake_get(run_id):
        return _fake_result()

    monkeypatch.setattr(backtest_manager, "get_run", fake_get)

    json_resp = await client.get("/api/v1/backtests/bt-5-6-001/export?format=json", headers=auth_headers)
    assert json_resp.status_code == 200
    assert json_resp.json()["run_id"] == "bt-5-6-001"
    assert json_resp.json()["summary"]["expectancy"] == 175.0

    csv_resp = await client.get("/api/v1/backtests/bt-5-6-001/export?format=csv", headers=auth_headers)
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert "expectancy" in csv_resp.text
    assert "NIFTY" in csv_resp.text


@pytest.mark.asyncio
async def test_export_pdf(monkeypatch, client, auth_headers):
    from routes.v1_backtest import backtest_manager

    async def fake_get(run_id):
        return _fake_result()

    monkeypatch.setattr(backtest_manager, "get_run", fake_get)

    resp = await client.get("/api/v1/backtests/bt-5-6-001/export?format=pdf", headers=auth_headers)
    if resp.status_code == 500 and "reportlab" in resp.json()["detail"].lower():
        pytest.skip("reportlab unavailable")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_export_bad_format(monkeypatch, client, auth_headers):
    from routes.v1_backtest import backtest_manager

    async def fake_get(run_id):
        return _fake_result()

    monkeypatch.setattr(backtest_manager, "get_run", fake_get)

    resp = await client.get("/api/v1/backtests/bt-5-6-001/export?format=docx", headers=auth_headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_export_missing_run_404(client, auth_headers):
    resp = await client.get("/api/v1/backtests/ghost/export?format=json", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_deploy_to_paper(monkeypatch, client, auth_headers):
    from builder.manager import builder_manager
    from builder.models import StrategyDSL, StrategyStatus
    from routes.v1_backtest import backtest_manager

    async def fake_get_run(run_id):
        return _fake_result()

    async def fake_get_strategy(sid):
        dsl = StrategyDSL(name="d", description="", settings={})
        dsl.status = StrategyStatus.READY
        return dsl

    async def fake_start(*, strategy_id, user_id, symbol, interval, is_paper):
        assert is_paper is True
        return "started"

    async def fake_set_status(sid, status):
        assert status == StrategyStatus.PAPER

    monkeypatch.setattr(backtest_manager, "get_run", fake_get_run)
    monkeypatch.setattr(builder_manager, "get", fake_get_strategy)
    monkeypatch.setattr("engine.graph_strategy_runner.start_graph_strategy", fake_start)
    monkeypatch.setattr(builder_manager, "set_status", fake_set_status)

    resp = await client.post(
        "/api/v1/backtests/bt-5-6-001/deploy-to-paper",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "started", "mode": "paper", "strategy_id": "abc123def456"}


@pytest.mark.asyncio
async def test_deploy_to_paper_builtin_rejected(monkeypatch, client, auth_headers):
    from routes.v1_backtest import backtest_manager

    async def fake_get_run(run_id):
        result = _fake_result()
        result.config.strategy_id = ""
        return result

    monkeypatch.setattr(backtest_manager, "get_run", fake_get_run)

    resp = await client.post(
        "/api/v1/backtests/bt-5-6-001/deploy-to-paper",
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "Only builder" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_candles_endpoint(monkeypatch, client, auth_headers):
    from backtest.historical import backtest_historical

    fake_candles = [{"time": "2026-01-05T10:00:00+00:00", "open": 100, "high": 101, "low": 99, "close": 100.5}]

    async def fake_load(**kwargs):
        assert kwargs["symbol"] == "NIFTY"
        assert kwargs["interval"] == "15m"
        assert kwargs["user_id"]
        return fake_candles

    monkeypatch.setattr(backtest_historical, "load", fake_load)

    resp = await client.get("/api/v1/backtests/candles/NIFTY/15m?days=30", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["candles"] == fake_candles


@pytest.mark.asyncio
async def test_corporate_actions_ingest_and_list(monkeypatch, client, auth_headers):
    from core.db import async_supabase, get_supabase

    class FakeQueryBuilder:
        def __init__(self):
            self.row = None

        def insert(self, row):
            self.row = row
            return self

        def select(self, *cols):
            return self

        def eq(self, k, v):
            return self

        def order(self, col, **kw):
            return self

        def limit(self, n):
            return self

        def execute(self):
            return self

        @property
        def data(self):
            return [self.row] if self.row else []

    fake_sb = FakeQueryBuilder()

    async def fake_async(call):
        return call()

    monkeypatch.setattr(get_supabase, "__call__", lambda *a, **k: fake_sb)
    monkeypatch.setattr(async_supabase, "__call__", fake_async)

    ingest = await client.post(
        "/api/v1/backtests/corporate-actions",
        json={"symbol": "NIFTY", "ex_date": "2026-01-01", "action": "SPLIT", "ratio": "1:2"},
        headers=auth_headers,
    )
    assert ingest.status_code == 200, ingest.text
    assert ingest.json()["ingested"]["symbol"] == "NIFTY"

    listing = await client.get("/api/v1/backtests/corporate-actions?symbol=NIFTY", headers=auth_headers)
    assert listing.status_code == 200


@pytest.mark.asyncio
async def test_static_routes_precede_run_id(monkeypatch, client, auth_headers):
    from backtest.historical import backtest_historical

    async def fake_load(**kwargs):
        return []

    monkeypatch.setattr(backtest_historical, "load", fake_load)

    resp = await client.get("/api/v1/backtests/candles/NIFTY/15m", headers=auth_headers)
    assert resp.status_code == 200, resp.text
