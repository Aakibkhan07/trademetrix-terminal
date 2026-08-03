# Deployment Checklist — Execution Engine v1.0 (2026-08-03)

Release commit: `4278f42` (fix: wire legacy bridge to real fill events +
shutdown re-init) on top of `b1cef9e` (feat: engine v1.0).
No schema / config / dependency changes — two Python files + tests + docs.

## 0. Pre-deploy gate (workstation)

- [ ] `git log --oneline -3` shows `4278f42` at HEAD, tree clean (except the
      uncommitted `infra/scripts/smoke_execution_engine*` smoke artifacts).
- [ ] Regression green: `cd apps/api && PYTHONPATH=. .venv/bin/python -m pytest
      tests/` → **762 passed, 1 xfailed** (baseline 757 + 5 new bridge/lifecycle tests).
- [ ] Engine suite only: `pytest tests/test_execution_engine.py` → 45 passed.
- [ ] Audit harness exit 0 (43/43) re-run against `HEAD` if any file touched.

## 1. Deploy to VPS

- [ ] `git push origin main` (only if authorized; deployment itself is covered
      by `infra/production/deploy.sh`).
- [ ] On VPS `root@187.127.185.56`:
      `cd /root/trademetrix-terminal && git fetch && git reset --hard origin/main`
- [ ] Hot-deploy (no rebuild needed — two files only):
  ```
  docker cp apps/api/execution_engine/events.py trademetrix_api:/app/execution_engine/events.py
  docker cp apps/api/execution_engine/init.py trademetrix_api:/app/execution_engine/init.py
  docker restart trademetrix_api
  ```
- [ ] Poll `https://api.ai.trademetrix.tech/health` → 200.

## 2. Post-deploy verification (quick)

- [ ] Log line present at startup:
      `Execution Engine v1.0 initialized (bus running=True, subscribers=...)`
- [ ] No `Legacy event bridge subscription failed` warning (the old TypeError
      must be gone).

## 3. Full smoke gate

Run the 15-minute production smoke (observes only; one `docker restart`):

```
TMX_VPS_PASSWORD='...' bash infra/scripts/smoke_execution_engine.sh
```

- [ ] Prints **`READY_FOR_PRODUCTION_DEPLOYMENT`** with all 15 items PASS:

1. Startup — engine initialized, bus running
2. Event bridge active (wired, no subscribe failure)
3. OMS → Engine propagation (order.filled log lines + trades gauge delta)
4. Paper order — OMS MARKET filled (FILLED, qty>0, avg>0)
5. Partial fill → 1 trade (PaperOrderPartiallyFilled)
6. Complete fill → 1 trade (PaperOrderFilled BUY / SELL)
7. Position update == reference FIFO (net 0)
8. P&L update — realized == reference (100.0)
9. Portfolio update — snapshot realized == position realized
10. Restart — API healthy, engine re-initialized, fills processed after restart
11. Health endpoint — GET /health 200
12. Metrics endpoint — GET /metrics exposes engine gauges
13. Memory usage — RSS growth < 100 MiB
14. No duplicate events (exactly 1 trade per probe fill id)
15. No event backlog (queue drained, ring bounded ≤ 2000)

- [ ] Any `[FAIL]` → do NOT deploy; fix, re-run gate, re-audit.

## Known-expected gaps (do NOT fail the gate)

- The OMS paper order may log **2** `event=order.filled` lines and increment
  the trades gauge by 2 (paper broker publishes `PaperOrderFilled` AND the OMS
  publishes `OrderCompleted` for the same fill → engine counts both). This is
  documented Known Limitation §2 (no fill-ack idempotency); the probe's
  per-fill-id dedupe (item 14) validates the fixed bridge path deterministically.