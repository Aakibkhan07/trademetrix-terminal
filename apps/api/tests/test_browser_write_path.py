"""The cookie and origin rules that decide whether a browser can write anything at all.

The CSRF assertion here drives the middleware and inspects the `Set-Cookie` the browser would see,
rather than matching the source text. A test that asserts a particular line exists passes or fails
on formatting, which is noise: it broke the moment the variable was renamed, while the behavioural
check kept passing and is the one that actually holds the line.

Both of these fail *silently*: reads keep working, the page looks healthy, and every POST answers
403. There is no error to trace — the request simply never reaches the handler.

## `SameSite=None` without `Secure` is not permissive, it is invalid

The CSRF cookie was set with `samesite="none"` and `secure=settings.env == "production"`. Outside
production that produced `SameSite=None` with no `Secure`, and a browser **rejects the cookie
entirely** — the spec requires `Secure` for `None`, and Chrome drops it rather than downgrading.

The result: `document.cookie` empty, `getCSRFToken()` in `apps/web/lib/api.ts` returned `''`,
`X-CSRF-Token` was never attached, and every POST/PUT/DELETE answered 403. Local development,
staging and any non-production deployment had **no working write path**, only reads.

## `localhost` and `127.0.0.1` cannot both be satisfied

Even with the cookie valid, the two halves of a local stack pull in opposite directions:

* cookies are host-scoped, so a page served from `http://localhost:3000` cannot read a cookie set
  by an API on `http://127.0.0.1:8000`
* `CORS_ORIGINS=http://localhost:3000` rejects the preflight from `http://127.0.0.1:3000` with a
  bodiless 400, which the browser reports as `net::ERR_FAILED` — the POST is never attempted

So one spelling fails on the cookie and the other fails on CORS, and reads still work either way.
Both loopback origins are now allowed outside production; production is untouched, because there the
origins are real hosts and widening an allow-list would be a security change.
"""
from __future__ import annotations

import pytest

from core.config import Settings


def _settings(**overrides) -> Settings:
    base = dict(
        env="development",
        cors_origins="http://localhost:3000",
        secret_key="x" * 32,
        supabase_url="https://example.supabase.co",
        supabase_service_key="service",
        supabase_anon_key="anon",
        encryption_key="y" * 32,
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


# ── the cookie attributes ─────────────────────────────────────────────────────

def _csrf_cookie_attrs(app) -> dict:
    """Pull the CSRF cookie's attributes off a real request through the app."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from starlette.middleware.base import BaseHTTPMiddleware

    from middleware.csrf import CSRFProtectMiddleware

    class _Mark(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            response.headers["x-test-csrf"] = "1"
            return response

    fastapi_app = FastAPI()
    fastapi_app.add_middleware(CSRFProtectMiddleware)
    fastapi_app.add_middleware(_Mark)

    @fastapi_app.get("/probe")
    async def _probe():  # pragma: no cover - trivial
        return {"ok": True}

    # The conftest `client` fixture avoids lifespan; here the app is local and has no lifespan,
    # so a plain TestClient is fine and keeps the assertion close to the middleware.
    with TestClient(fastapi_app) as c:
        r = c.get("/probe")
    raw = r.headers.get("set-cookie", "")
    out = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip().lower()] = v
        elif part:
            out[part.lower()] = True
    return out


def test_csrf_cookie_attributes_are_valid_together(monkeypatch):
    """Drive the middleware directly and assert the browser-visible attributes are coherent."""
    import asyncio

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from middleware.csrf import CSRFProtectMiddleware

    settings = _settings(env="development")
    monkeypatch.setattr("middleware.csrf.settings", settings)

    app = FastAPI()
    app.add_middleware(CSRFProtectMiddleware)

    @app.get("/probe")
    async def _probe():  # pragma: no cover - trivial
        return {"ok": True}

    with TestClient(app) as c:
        raw = c.get("/probe").headers.get("set-cookie", "")

    assert "csrf_token=" in raw, f"no CSRF cookie was set: {raw!r}"
    low = raw.lower()
    has_secure = "secure" in low
    has_none = "samesite=none" in low.replace(" ", "")
    assert not (has_none and not has_secure), (
        f"SameSite=None without Secure — a browser drops this cookie outright: {raw!r}"
    )


# ── the origin list ───────────────────────────────────────────────────────────

def test_loopback_aliases_are_added_outside_production():
    assert _settings(env="development").cors_origin_list == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_production_origin_list_is_exactly_what_was_configured():
    """Adding an alias in production would be a security change, not a convenience."""
    configured = ["https://ai.trademetrix.tech", "https://app.trademetrix.tech"]
    got = _settings(env="production", cors_origins=",".join(configured)).cors_origin_list
    assert got == configured, f"production list was widened: {got}"


def test_non_loopback_origins_are_never_widened():
    """A real host must not gain a sibling just because it is in the list."""
    got = _settings(env="development", cors_origins="https://ai.trademetrix.tech").cors_origin_list
    assert got == ["https://ai.trademetrix.tech"]


def test_ports_and_paths_are_preserved_when_aliasing():
    got = _settings(env="development", cors_origins="http://localhost:5173/app").cors_origin_list
    assert "http://127.0.0.1:5173/app" in got, "the alias must keep the port and path"


def test_a_list_literal_is_parsed_and_widened():
    got = _settings(env="development", cors_origins="['http://localhost:3000']").cors_origin_list
    assert "http://127.0.0.1:3000" in got


def test_aliases_are_not_duplicated():
    got = _settings(
        env="development",
        cors_origins="http://localhost:3000,http://127.0.0.1:3000",
    ).cors_origin_list
    assert len(got) == len(set(got)) == 2, f"duplicate origins: {got}"


@pytest.mark.parametrize("raw,expected", [
    ("", []),
    ("   ", []),
])
def test_empty_origin_lists_stay_empty(raw, expected):
    assert _settings(env="development", cors_origins=raw).cors_origin_list == expected