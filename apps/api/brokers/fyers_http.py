"""Fyers REST transport — thin Fyers facade over the generic broker transport.

All rate-limit, retry, dedup, cache and accounting behavior lives in
``brokers.sdk.transport.HttpTransport``; this module only supplies Fyers'
budgets, endpoints, headers, auth scheme and error translation.  The public
API (``FyersTransport``, ``FyersResponse``, ``FyersWAFError``,
``TokenRateLimiter``, ``get_transport``, ``fyers_rate_snapshot``) is
unchanged for existing callers.
"""

from __future__ import annotations

from typing import Any

from brokers.sdk.errors import BrokerWAFError
from brokers.sdk.transport import (
    AuthStrategy,
    ErrorTranslator,
    HeaderStrategy,
    HttpTransport,
    RateLimiter,
    TokenRateLimiter,
    TransportConfig,
    TransportResponse,
    URLBuilder,
)

# Back-compat alias — callers import the response type from here.
FyersResponse = TransportResponse

# ---------------------------------------------------------------------------
# Budgets — Fyers' public ceiling is ~200 req/min per token (observed in the
# wild; the T&C reserve the right to enforce limits). We target < 50% of that.
# ---------------------------------------------------------------------------
FYERS_RPM_LIMIT = 100       # sustained requests per minute per access token
FYERS_BURST_PER_SECOND = 8  # per-second burst ceiling
BACKOFF_BASE_SECONDS = 0.25
BACKOFF_CAP_SECONDS = 8.0
MAX_RETRIES = 3

_BROWSER_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://myapi.fyers.in",
    "Referer": "https://myapi.fyers.in/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

_FYERS_BASE_URL = "https://api-t1.fyers.in"


class FyersWAFError(BrokerWAFError):
    """Raised when Fyers/Cloudflare returns HTTP 403 (WAF block).

    These must never be retried in a tight loop — a 403 means the request was
    rejected before reaching the auth layer (e.g. datacenter IP blocked on an
    endpoint).
    """


class FyersAuthStrategy(AuthStrategy):
    """Fyers auth: ``Authorization: {client_id}:{access_token}``."""

    def authorization(self, client_id: str, access_token: str) -> str | None:
        if not access_token:
            return None
        return f"{client_id}:{access_token}"


class FyersHeaderStrategy(HeaderStrategy):
    """Browser-identical headers so Cloudflare does not fingerprint us."""

    def __init__(self):
        super().__init__(static_headers=_BROWSER_HEADERS)


class FyersURLBuilder(URLBuilder):
    """Fyers hosts: ``api-t1.fyers.in`` API + data, ``public.fyers.in`` CSVs."""

    def __init__(self):
        super().__init__(base_url=_FYERS_BASE_URL)

    def stub(self, url: str) -> str:
        if url.startswith("https://public.fyers.in/"):
            return url.split("sym_details/")[-1].split("?")[0]
        return url.split("?")[0].split("api-t1.fyers.in")[-1].split("api.fyers.in")[-1] or url


class FyersErrorTranslator(ErrorTranslator):
    """Maps 403 (Cloudflare WAF block) onto ``FyersWAFError`` — never retried."""

    def translate(self, status: int, raw: Any, path_stub: str, broker: str = "") -> Exception | None:
        if status == 403:
            body = getattr(raw, "text", "")[:300]
            return FyersWAFError(
                f"Fyers/Cloudflare WAF blocked request to {path_stub} (HTTP 403): {body[:120]}",
                broker=broker,
            )
        return None


class FyersTransport(HttpTransport):
    """Rate-limited, retrying, deduplicating, caching Fyers HTTP transport.

    One instance per ``client_id`` (access token) so that all adapter/caller
    instances for the same token share one limiter, one connection pool and one
    RPM ledger.
    """

    def __init__(self, client_id: str = "", access_token: str = ""):
        config = TransportConfig(
            broker="fyers",
            base_url=_FYERS_BASE_URL,
            rpm=FYERS_RPM_LIMIT,
            burst=FYERS_BURST_PER_SECOND,
            backoff_base_seconds=BACKOFF_BASE_SECONDS,
            backoff_cap_seconds=BACKOFF_CAP_SECONDS,
            max_retries=MAX_RETRIES,
            timeout_seconds=30.0,
            impersonate="chrome131",
            log_prefix="fyers",
        )
        limiter = _limiters.get(client_id) or RateLimiter(
            client_id or "anon", rpm=FYERS_RPM_LIMIT, burst=FYERS_BURST_PER_SECOND
        )
        _limiters[client_id] = limiter

        super().__init__(
            config,
            client_id=client_id,
            access_token=access_token,
            limiter=limiter,
            auth=FyersAuthStrategy(),
            headers=FyersHeaderStrategy(),
            url_builder=FyersURLBuilder(),
            translator=FyersErrorTranslator(),
        )

    @staticmethod
    def _path_stub(url: str) -> str:
        """Back-compat: stats key for a URL (kept for external callers)."""
        return FyersURLBuilder().stub(url)


# Registry: one transport per access token (client_id), shared process-wide so
# rate accounting is global per token regardless of how many adapter instances
# or callers exist.
_transports: dict[str, FyersTransport] = {}
_limiters: dict[str, RateLimiter] = {}


def get_transport(client_id: str = "", access_token: str = "") -> FyersTransport:
    key = client_id or "anon"
    tr = _transports.get(key)
    if tr is None:
        tr = FyersTransport(client_id=client_id, access_token=access_token)
        _transports[key] = tr
    elif access_token:
        tr.set_token(client_id, access_token)
    return tr


def fyers_rate_snapshot() -> dict[str, Any]:
    """Aggregate RPM/retry ledger across all active tokens (for metrics/admin)."""
    return {
        "budget_rpm_per_token": FYERS_RPM_LIMIT,
        "burst_per_second": FYERS_BURST_PER_SECOND,
        "tokens": [
            tr.snapshot()
            for tr in _transports.values()
            if tr._stats or tr._limiter.pending_in_window(60)
        ],
    }
