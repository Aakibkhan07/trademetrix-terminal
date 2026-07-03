# Development Roadmap

> Phases are ordered by priority. Each phase should be completed before starting the next.

---

## Phase 1: Audit & Documentation (CURRENT)

**Goal**: Understand the full codebase, identify issues, document everything.

| # | Task | Status | Est. Effort |
|---|------|--------|-------------|
| 1.1 | Explore repository structure | ✅ DONE | 1h |
| 1.2 | Audit backend routes | ✅ DONE | 2h |
| 1.3 | Audit broker adapters | ✅ DONE | 3h |
| 1.4 | Audit market data engine | ✅ DONE | 2h |
| 1.5 | Audit frontend components | ✅ DONE | 2h |
| 1.6 | Generate Architecture.md | ✅ DONE | 1h |
| 1.7 | Generate ProjectAudit.md | ✅ DONE | 1h |
| 1.8 | Generate MissingFeatures.md | ✅ DONE | 1h |
| 1.9 | Generate Roadmap.md | ✅ DONE | 1h |

**Goal**: Zero code changes. Full documentation of architecture, issues, and gaps.

---

## Phase 2: Critical Fixes

**Goal**: Fix bugs found in Phase 1 that block functionality or risk production stability.

| # | Task | Est. Effort | Dependencies |
|---|------|-------------|--------------|
| 2.1 | Add unit tests for all API routes (pytest + TestClient) | 3d | None |
| 2.2 | Add unit tests for broker adapters (mocked HTTP) | 2d | None |
| 2.3 | Implement Dhan OAuth flow | 1d | Fyers adapter as reference |
| 2.4 | Implement Upstox OAuth flow | 1d | Fyers adapter as reference |
| 2.5 | Live-test AliceBlue stream() with real credentials | 4h | Real AliceBlue account |
| 2.6 | Live-test Finvasia stream() with real credentials | 4h | Real Finvasia account |
| 2.7 | Live-test FlatTrade stream() with real credentials | 4h | Real FlatTrade account |
| 2.8 | Live-test KotakNeo stream() with real credentials | 4h | Real Kotak Neo account |

**Priority**: HIGH — without tests, no changes are safe. Without OAuth for Dhan/Upstox, 2 brokers are unusable.

---

## Phase 3: Performance & Scalability

**Goal**: Ensure the platform handles real-world traffic and data volumes.

| # | Task | Est. Effort | Dependencies |
|---|------|-------------|--------------|
| 3.1 | Add pagination to all list endpoints | 1d | None |
| 3.2 | Add pagination controls to frontend tables | 1d | 3.1 |
| 3.3 | Implement WebSocket reconnection backoff | 4h | None |
| 3.4 | Add Ornstein-Uhlenbeck price simulation (mean reversion) | 4h | None |
| 3.5 | Auto-start alert checker on API boot | 4h | None |
| 3.6 | Add rate limit response headers | 2h | None |

**Priority**: MEDIUM — necessary before public launch or significant user growth.

---

## Phase 4: Feature Completion

**Goal**: Fill gaps in the current feature set.

| # | Task | Est. Effort | Dependencies |
|---|------|-------------|--------------|
| 4.1 | Deprecate duplicate Jinja2 admin template | 2h | Confirm which is in use |
| 4.2 | Add SEO metadata, sitemap, robots.txt | 4h | None |
| 4.3 | Add order modification/cancellation UI | 1d | None |
| 4.4 | Add multi-user alert broadcasting (admin) | 1d | None |
| 4.5 | Add TOTP 2FA for admin accounts | 2d | None |
| 4.6 | Add API key management system | 2d | None |
| 4.7 | Add retry with backoff to broker adapters | 1d | None |

**Priority**: LOW — valuable additions but not blocking core functionality.

---

## Phase 5: Polish & Launch

**Goal**: Production readiness.

| # | Task | Est. Effort | Dependencies |
|---|------|-------------|--------------|
| 5.1 | Load testing (k6 or similar) | 1d | Phase 3 |
| 5.2 | Security audit (dependency scan, OWASP checks) | 1d | None |
| 5.3 | Documentation: user guide | 2d | None |
| 5.4 | Documentation: API reference (OpenAPI spec) | 1d | None |
| 5.5 | Monitoring setup (health checks, logging, alerts) | 1d | None |
| 5.6 | CI/CD pipeline (GitHub Actions) | 1d | Phase 2 (tests) |

**Priority**: MEDIUM — necessary for public launch.

---

## Summary

| Phase | Effort | Priority |
|-------|--------|----------|
| 1. Audit & Documentation | ~14h | 🔴 NOW |
| 2. Critical Fixes | ~8d | 🔴 HIGH |
| 3. Performance & Scalability | ~3d | 🟡 MEDIUM |
| 4. Feature Completion | ~8d | 🟢 LOW |
| 5. Polish & Launch | ~6d | 🟡 MEDIUM |

**Total estimated effort**: ~24 days (full-time) to production readiness.
