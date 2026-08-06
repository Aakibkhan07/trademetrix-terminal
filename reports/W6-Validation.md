# W6 — Validation Report

All validation gates executed on the final tree (web-only commit), **before** production deploy.

## 1. TypeScript

```
$ npx tsc --noEmit            (apps/web)
exit 0 — 0 errors
```

## 2. Lint

```
$ npm run lint                (apps/web)
exit 0 — 0 errors
1 pre-existing warning: components/workspace/strategy-builder/deploy-wizard.tsx:64:6
  (react-hooks/exhaustive-deps, `draft.confirm_live` — not introduced by this sprint)
```

## 3. Production build

```
$ npm run build               (apps/web)
Build succeeded — middleware 40.1 kB, First Load JS shared 84.6 kB
No errors, no type errors, no lint-block errors.
```

Selected route first-load sizes (new build):

| Route | Route JS | First Load |
|---|---|---|
| `/backtest` | 17.4 kB | 162 kB |
| `/marketdata` | 7.07 kB | 156 kB |
| `/portfolio` | 7.3 kB | 113 kB |
| `/strategies/builder` | 13.9 kB | 109 kB |
| `/strategies/[key]` | 3.35 kB | 98.5 kB |
| `/strategies` | 4.05 kB | 99.2 kB |
| `/terminal/builder` | 8.72 kB | 97.1 kB |
| `/admin/beta` | 7.27 kB | 95.6 kB |
| `/backtest` (consolidated) | 17.4 kB | 162 kB |
| `/admin/admins` | 3.51 kB | 91.8 kB |
| `/strategies/catalog` | 3.23 kB | 91.6 kB |

## 4. API regression (untouched cross-check)

```
$ cd apps/api && .venv/bin/python -m pytest tests/ -q
955 passed, 1 xfailed, 8 warnings in 32.66s
```
Matches Sprint-2 baseline exactly → no API drift from this sprint.

## 5. Visual/regression

- SSR HTML parity (12 production routes, pre/post deploy): see `W6-Visual-Verification.md` — all identical after normalization.
- Route sweep: all 12 routes HTTP 200 pre- and post-deploy.

## 6. Post-deploy smoke (after push per `infra/deploy-prod.sh`)

- Health endpoints + key public routes re-verified 200 in production.
- No console/exception errors in app routes (server-rendered shells match pre-deploy).

## Summary

| Gate | Result |
|---|---|
| TypeScript | Pass |
| ESLint | Pass (1 pre-existing warning) |
| Build | Pass |
| API regression | 955 pass / 1 xfail (baseline) |
| Visual parity | Pass (12/12 routes identical) |
| Post-deploy smoke | Pass |