# Rollback Checklist — Execution Engine v1.0 (2026-08-03)

Trigger when the post-deploy smoke gate fails, `/health` degrades, or engine
metrics/logs show regressions after deploying `4278f42`.

## 0. Preconditions

- [ ] Confirm the release commit: `git log --oneline -3` shows `4278f42`
      (fix) on `b1cef9e` (feat).
- [ ] The engine change set is the **new `execution_engine/` package** plus two
      modified files: `apps/api/main.py`, `apps/api/portfolio/manager.py`
      (+ tests/docs, not needed on prod). Rolling back cannot touch schema,
      config, deps, or other modules.
- [ ] No data migration exists for the engine; rollback is state-preserving
      (engine state is in-memory + Prometheus counters).

## 1. Immediate mitigation (≤ 1 min)

- [ ] If symptoms are severe (API unhealthy, error loops): `docker restart
      trademetrix_api` once. If the API stays unhealthy, skip ahead — the
      engine fix does not gate the API (bridge failure was pre-existing and
      only logged).
- [ ] Otherwise proceed through the normal rollback below.

## 2. Normal rollback

- [ ] `git revert 4278f42` locally, or `git reset --hard b1cef9e` (last known
      good = the feat commit, whose bridge was wired-but-inert).
- [ ] `git push origin main` (if authorized).
- [ ] On VPS `root@187.127.185.56`:
      `cd /root/trademetrix-terminal && git fetch && git reset --hard origin/main`
- [ ] Re-deploy the reverted files:
  ```
  docker cp apps/api/execution_engine trademetrix_api:/app/execution_engine
  docker cp apps/api/main.py trademetrix_api:/app/main.py
  docker cp apps/api/portfolio/manager.py trademetrix_api:/app/portfolio/manager.py
  docker restart trademetrix_api
  ```

## 3. Verify rollback

- [ ] `https://api.ai.trademetrix.tech/health` → 200.
- [ ] Startup log line:
      `Execution Engine v1.0 initialized (bus running=True, subscribers=...)`.
- [ ] Expected degraded behavior (NOT failures): the legacy bridge does not
      forward fills (`execution.event event=order.filled` lines absent) and
      `execution_engine_trades_executed_total` stays flat — identical to the
      pre-fix production state. No error spam; at most the old single
      `Legacy event bridge subscription failed` warning.
- [ ] OMS / orders / platform endpoints unaffected (they do not depend on the
      engine bridge).

## 4. Post-rollback

- [ ] Open a follow-up: re-audit (43/43 harness), re-run regression
      (762 passed / 1 xfailed), fix, re-open the deployment checklist.
- [ ] Record the rollback + root cause in CHANGELOG / incident notes.