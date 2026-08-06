"""Sprint 1 production smoke — W1 canonical metrics verification (in-container)."""
import asyncio
import sys

import httpx

sys.path.insert(0, "/app")
from core.security import create_access_token

API = "https://api.ai.trademetrix.tech"
USER = "fa668109-4b1e-4758-a49b-015027ea4115"

REQ = {
    "strategy_type": "macd_cross",
    "symbol": "NSE:NIFTY50-INDEX",
    "exchange": "NSE",
    "interval": "15m",
    "days": 60,
    "initial_capital": 1000000,
    "config": {"symbol": "NSE:NIFTY50-INDEX"},
    "slippage_pct": 0.05,
    "brokerage_pct": 0.03,
    "stt_pct": 0.025,
    "exchange_pct": 0.003,
}

REQ_V2 = {
    "strategy_type": "macd_cross",
    "symbol": "NSE:NIFTY50-INDEX",
    "exchange": "NSE",
    "interval": "15m",
    "days": 60,
    "initial_capital": 1000000,
    "strategy_params": {"symbol": "NSE:NIFTY50-INDEX"},
    "speed": "MAX",
    "data_source": "auto",
    "file_path": "",
    "risk_enabled": False,
    "close_positions_on_end": True,
}

KEYS = ["total_trades", "winning_trades", "losing_trades", "win_rate", "total_pnl",
        "max_drawdown", "sharpe_ratio", "avg_win", "avg_loss", "largest_win",
        "largest_loss", "trades", "equity_curve"]

results: dict[str, str] = {}


def report(name: str, ok: bool, detail: str = "") -> None:
    results[name] = "PASS" if ok else "FAIL"
    print(f"[{results[name]}] {name} {detail}")


def old_paper_formula(cfg, gross: float, side: str) -> tuple:
    commission = gross * cfg.commission_pct / 100
    exchange = gross * cfg.exchange_charges_pct / 100
    stt = gross * cfg.stt_pct / 100
    stamp = gross * cfg.stamp_duty_pct / 100
    total = commission + exchange + stt + stamp
    net = gross + total if side == "BUY" else gross - total
    return round(commission, 2), round(exchange, 2), round(stt, 2), round(stamp, 2), round(net, 2)


async def main() -> None:
    async with httpx.AsyncClient(base_url=API, verify=False, timeout=180.0) as c:
        csrf = await c.get("/api/v1/auth/csrf")
        body_token = csrf.json().get("csrf_token")
        c.cookies.set("csrf_token", body_token)
        h = {"Authorization": f"Bearer {token}", "X-CSRF-Token": body_token}

        r1 = await c.post("/api/v1/backtests/run", json=REQ, headers=h)
        report("legacy_run_200", r1.status_code == 200, str(r1.status_code))
        j1 = r1.json()
        res1 = j1["results"]
        report("legacy_payload_keys", all(k in res1 for k in KEYS))
        report("legacy_sharpe_present", "sharpe_ratio" in res1, f"sharpe={res1['sharpe_ratio']} trades={res1['total_trades']}")

        r2 = await c.post("/api/v1/backtests/", json=REQ, headers=h)
        report("create_backtest_201", r2.status_code == 201, str(r2.status_code))
        res2 = r2.json()["results"]
        identical = all(res1[k] == res2[k] for k in KEYS)
        report("legacy_run_equals_create", identical,
               f"sharpe {res1['sharpe_ratio']} vs {res2['sharpe_ratio']}, trades {res1['total_trades']} vs {res2['total_trades']}")

        r3 = await c.post("/api/v1/backtests/run-v2", json=REQ_V2, headers=h)
        report("run_v2_200", r3.status_code == 200, str(r3.status_code))
        j3 = r3.json()
        s = j3.get("summary", {})
        report("run_v2_sharpe_present", "sharpe_ratio" in s, f"sharpe={s.get('sharpe_ratio')} trades={s.get('total_trades')}")

        run_id = j3.get("run_id")
        if run_id:
            r4 = await c.get(f"/api/v1/backtests/{run_id}", headers=h)
            report("get_run_200", r4.status_code == 200, str(r4.status_code))
            trades = r4.json().get("trades", [])
            enriched = [t for t in trades if "cost_total" in t]
            bad = [
                t for t in enriched
                if abs(t.get("cost_total", -1) - (t.get("slippage", 0) + t.get("charges", 0) + t.get("taxes", 0))) > 0.01
            ]
            report("fee_parity_cost_total", len(bad) == 0,
                   f"{len(enriched)}/{len(trades)} enriched, mismatches={len(bad)}")
            if enriched:
                t = enriched[0]
                report("fee_fields_present", all(k in t for k in ("slippage", "charges", "taxes", "cost_total")),
                       f"e.g. {t.get('cost_total')} = {t.get('slippage')}+{t.get('charges')}+{t.get('taxes')}")
            r5 = await c.get(f"/api/v1/backtests/{run_id}/export?format=json", headers=h)
            report("export_json_200", r5.status_code == 200, str(r5.status_code))

    # Paper fill parity (direct, offline — same code the prod container runs)
    from core.models import Exchange, InstrumentType, NormalizedOrder, OrderSide, OrderType, ProductType
    from paper.fill_engine import FillEngine
    from paper.models import PaperConfig

    order = NormalizedOrder(symbol="TST", exchange=Exchange.NSE, side=OrderSide.BUY,
                            order_type=OrderType.MARKET, product=ProductType.INTRADAY,
                            quantity=10, instrument_type=InstrumentType.EQ)
    for cfg in (PaperConfig(), PaperConfig(commission_pct=0.05, exchange_charges_pct=0.01,
                                           stt_pct=0.01, stamp_duty_pct=0.003)):
        fill = FillEngine(cfg)._build_fill(order, 10, 100.0)
        old = old_paper_formula(cfg, 1000.0, "BUY")
        new = (fill.commission, fill.exchange_charges, fill.stt, fill.stamp_duty, fill.net_amount)
        ok = all(abs(a - b) < 0.011 for a, b in zip(old, new))
        report(f"paper_fill_parity_{cfg.commission_pct}", ok, f"old={old} new={new}")

    failed = [k for k, v in results.items() if v != "PASS"]
    print(f"\nSUMMARY: {len(results) - len(failed)}/{len(results)} PASS; failures={failed}")


token = create_access_token(USER)
asyncio.run(main())
