"""Fyers REST transport with rate-limit compliance.

Centralizes every Fyers HTTP call so that:

- A **per-token sliding-window limiter** (sustained RPM + per-second burst) keeps
  us well below Fyers' observed ~200 req/min ceiling per access token.
- **HTTP 429 and Cloudflare 1015** are respected: honor ``Retry-After`` when
  present, otherwise sleep with exponential backoff + full jitter. 403
  (Cloudflare WAF block) is NOT retried — it raises ``FyersWAFError``.
- **No tight retry loops**: every retry sleeps ``base * 2**attempt`` jittered;
  timeouts/5xx/521 get the same treatment.
- **Identical requests are deduplicated**: concurrent in-flight calls for the
  same (method, path, body) await a single HTTP round-trip.
- **Static responses are cached**: callers pass ``cache_ttl`` per endpoint
  (orders/positions/funds/holdings short TTLs, history/option-chain/margin
  longer, symbol CSVs 24h).
- **RPM accounting + structured logging**: per-endpoint rolling counters
  (calls, wire calls, cache hits, dedup hits, retries, 429/1015 events) are
  exposed via ``fyers_rate_snapshot()`` and logged as
  ``fyers.request`` / ``fyers.retry`` records.
"""

import asyncio
import hashlib
import json
import logging
import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import httpx
from curl_cffi.requests import AsyncSession

logger = logging.getLogger("brokers.fyers_http")

# ---------------------------------------------------------------------------
# Budgets — Fyers' public ceiling is ~200 req/min per token (observed in the
# wild; the T&C reserve the right to enforce limits). We target < 50% of that.
# ---------------------------------------------------------------------------
FYERS_RPM_LIMIT = 100       # sustained requests per minute per access token
FYERS_BURST_PER_SECOND = 8  # per-second burst ceiling
BACKOFF_BASE_SECONDS = 0.25
BACKOFF_CAP_SECONDS = 8.0
MAX_RETRIES = 3

# Retryable HTTP statuses: rate limiting (429, 1015) and transient 5xx.
RETRYABLE_HTTP = {429, 500, 502, 503, 504, 521, 1015}
# Retryable transport errors (network blips, timeouts, resets).
RETRYABLE_NET = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    httpx.ReadError,
    httpx.TransportError,
)

_BROWSER_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://myapi.fyers.in",
    "Referer": "https://myapi.fyers.in/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}


class FyersWAFError(Exception):
    """Raised when Fyers/Cloudflare returns HTTP 403 (WAF block).

    These must never be retried in a tight loop — a 403 means the request was
    rejected before reaching the auth layer (e.g. datacenter IP blocked on an
    endpoint)."""


@dataclass
class FyersResponse:
    """Minimal httpx-like response so existing ``_safe_json`` parsers keep working."""

    status_code: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def text(self) -> str:
        try:
            return self.body.decode("utf-8", "replace")
        except Exception:
            return ""

    def json(self):
        return json.loads(self.text)

    @property
    def ok(self) -> bool:
        return self.status_code < 400


class TokenRateLimiter:
    """Sliding-window rate limiter for a single Fyers access token.

    Enforces both the sustained RPM budget and a per-second burst ceiling.
    ``acquire()`` sleeps until a slot frees up (never fails, never tight-loops).
    """

    def __init__(self, key: str, rpm: int = FYERS_RPM_LIMIT, burst: int = FYERS_BURST_PER_SECOND, window_seconds: float = 60.0):
        self.key = key
        self.rpm = rpm
        self.burst = burst
        self.window = window_seconds
        self._hits: deque[float] = deque()
        self._lock = asyncio.Lock()

    def _prune(self, now: float) -> None:
        cutoff = now - self.window
        while self._hits and self._hits[0] < cutoff:
            self._hits.popleft()

    async def acquire(self) -> float:
        async with self._lock:
            now = time.monotonic()
            self._prune(now)
            wait = 0.0
            if len(self._hits) >= self.rpm:
                wait = max(wait, self._hits[0] + self.window - now)
            recent_second = [t for t in self._hits if t > now - 1.0]
            if len(recent_second) >= self.burst:
                wait = max(wait, min(recent_second) + 1.0 - now)
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()
                self._prune(now)
            self._hits.append(now)
            return wait

    def pending_in_window(self, seconds: int = 60) -> int:
        now = time.monotonic()
        self._prune(now)
        return len(self._hits)

@dataclass
class EndpointStats:
    """Rolling 60s accounting for one Fyers endpoint (path only)."""

    path: str
    calls: int = 0              # logical calls (incl. cache/dedup hits)
    wire_calls: int = 0         # actual HTTP round-trips
    cache_hits: int = 0
    dedup_hits: int = 0
    retries: int = 0            # total retry attempts (all reasons)
    rate_limited: int = 0       # 429/1015 responses seen
    waf_blocked: int = 0        # 403 WAF blocks seen
    failures: int = 0           # final failures (non-2xx after retries)
    first_seen: float = field(default_factory=time.monotonic)
    last_seen: float = field(default_factory=time.monotonic)

    def rpm(self) -> float:
        elapsed = max(self.last_seen - self.first_seen, 1.0)
        return round(self.calls / elapsed * 60.0, 1)


class FyersTransport:
    """Rate-limited, retrying, deduplicating, caching Fyers HTTP transport.

    One instance per ``client_id`` (access token) so that all adapter/caller
    instances for the same token share one limiter, one connection pool and one
    RPM ledger.
    """

    def __init__(self, client_id: str = "", access_token: str = ""):
        self.client_id = client_id
        self.access_token = access_token
        self._limiter = _limiters.get(client_id) or TokenRateLimiter(client_id or "anon")
        _limiters[client_id] = self._limiter
        self._client: AsyncSession | None = None
        self._cache: dict[str, tuple[float, FyersResponse]] = {}
        self._inflight: dict[str, asyncio.Future] = {}
        self._stats: dict[str, EndpointStats] = {}
        self._lock = asyncio.Lock()

    # -- shared client ------------------------------------------------------

    async def _get_client(self) -> AsyncSession:
        if self._client is None:
            self._client = AsyncSession(impersonate="chrome131", timeout=30.0)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None

    def set_token(self, client_id: str, access_token: str) -> None:
        self.client_id = client_id
        self.access_token = access_token

    # -- stats --------------------------------------------------------------

    def _stats_for(self, path: str) -> EndpointStats:
        st = self._stats.get(path)
        if st is None:
            st = EndpointStats(path=path)
            self._stats[path] = st
        st.last_seen = time.monotonic()
        return st

    def snapshot(self) -> dict[str, Any]:
        return {
            "token": self.client_id or "anon",
            "budget_rpm": self._limiter.rpm,
            "burst_per_second": self._limiter.burst,
            "used_last_minute": self._limiter.pending_in_window(60),
            "endpoints": sorted(
                (
                    {
                        "path": st.path,
                        "calls": st.calls,
                        "wire_calls": st.wire_calls,
                        "rpm": st.rpm(),
                        "cache_hits": st.cache_hits,
                        "dedup_hits": st.dedup_hits,
                        "retries": st.retries,
                        "rate_limited": st.rate_limited,
                        "waf_blocked": st.waf_blocked,
                        "failures": st.failures,
                    }
                    for st in self._stats.values()
                ),
                key=lambda e: e["rpm"],
                reverse=True,
            ),
        }

    # -- request ------------------------------------------------------------

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
        cache_ttl: float = 0.0,
        dedup: bool = True,
        retries: int = MAX_RETRIES,
        caller: str = "",
        authenticated: bool = True,
    ) -> FyersResponse:
        """Execute one Fyers API call with rate limiting, retry, dedup, cache.

        ``path`` is a full URL or a path under the Fyers base hosts.
        ``cache_ttl > 0`` (GET only) caches successful 2xx bodies.
        ``dedup`` collapses concurrent identical requests into one round-trip.
        Raises ``FyersWAFError`` on 403; otherwise returns the final response.
        """
        if not path.startswith("http"):
            path = f"https://api-t1.fyers.in{path}"

        path_stub = self._path_stub(path)
        st = self._stats_for(path_stub)
        st.calls += 1

        cache_key = self._cache_key(method, path, json_body, params)
        if method.upper() == "GET" and cache_ttl > 0:
            cached = self._cache.get(cache_key)
            if cached and cached[0] > time.monotonic():
                st.cache_hits += 1
                logger.info(
                    "fyers.request endpoint=%s method=%s status=%s retries=%d latency_ms=0.0 cached=1 dedup=0 rate_rpm=%.1f caller=%s",
                    path_stub, method.upper(), cached[1].status_code, 0, st.rpm(), caller or "-",
                )
                return cached[1]

        if dedup:
            existing = self._inflight.get(cache_key)
            if existing is not None:
                try:
                    resp = await asyncio.shield(existing)
                    st.dedup_hits += 1
                    logger.info(
                        "fyers.request endpoint=%s method=%s status=%s retries=%d latency_ms=0.0 cached=0 dedup=1 rate_rpm=%.1f caller=%s",
                        path_stub, method.upper(), resp.status_code, 0, st.rpm(), caller or "-",
                    )
                    return resp
                except Exception:
                    pass  # fell through — retry path below lost the race

        if dedup:
            future: asyncio.Future = asyncio.get_running_loop().create_future()
            self._inflight[cache_key] = future
        try:
            resp, retry_count, wait_sum = await self._execute_with_retries(
                method, path, json_body, params, retries, st, caller, authenticated
            )
            if method.upper() == "GET" and cache_ttl > 0 and resp.status_code < 400:
                self._cache[cache_key] = (time.monotonic() + cache_ttl, resp)
                while len(self._cache) > 1024:
                    self._cache.pop(next(iter(self._cache)), None)
            logger.info(
                "fyers.request endpoint=%s method=%s status=%d retries=%d latency_ms=%.1f cached=0 dedup=0 rate_rpm=%.1f caller=%s",
                path_stub, method.upper(), resp.status_code, retry_count, wait_sum * 1000, st.rpm(), caller or "-",
            )
            if dedup and not future.done():
                future.set_result(resp)
            return resp
        except BaseException as e:
            if dedup and not future.done():
                future.set_exception(e)
            raise
        finally:
            if dedup:
                self._inflight.pop(cache_key, None)

    async def _execute_with_retries(
        self,
        method: str,
        path: str,
        json_body: dict | None,
        params: dict | None,
        retries: int,
        st: EndpointStats,
        caller: str,
        authenticated: bool = True,
    ):
        client = await self._get_client()
        headers = dict(_BROWSER_HEADERS)
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        if authenticated and self.access_token:
            headers["Authorization"] = f"{self.client_id}:{self.access_token}"

        attempt = 0
        total_wait = 0.0
        while True:
            await self._limiter.acquire()
            started = time.monotonic()
            try:
                if method.upper() == "GET":
                    resp = await client.get(path, params=params, headers=headers)
                elif method.upper() == "DELETE":
                    resp = await client.delete(path, json=json_body, headers=headers)
                else:
                    resp = await client.post(path, json=json_body, headers=headers) if method.upper() == "POST" else await client.patch(path, json=json_body, headers=headers)
            except RETRYABLE_NET as e:
                wire = FyersResponse(status_code=0, body=b"", headers={})
                st.wire_calls += 1
                if attempt >= retries:
                    st.failures += 1
                    logger.warning(
                        "fyers.retry endpoint=%s method=%s error=transport retries=%d attempt=%d/%d caller=%s",
                        self._path_stub(path), method.upper(), retries, attempt + 1, retries + 1, caller or "-",
                    )
                    raise
                delay = self._backoff(attempt, st, reason="transport")
                total_wait += delay
                await asyncio.sleep(delay)
                attempt += 1
                st.retries += 1
                logger.info(
                    "fyers.retry endpoint=%s method=%s status=transport-error retries=%d attempt=%d/%d delay=%.2fs caller=%s",
                    self._path_stub(path), method.upper(), retries, attempt, retries + 1, delay, caller or "-",
                )
                continue

            st.wire_calls += 1
            status = resp.status_code

            if status == 403:
                st.waf_blocked += 1
                body = getattr(resp, "text", "")[:300]
                logger.error(
                    "fyers.waf endpoint=%s method=%s status=403 retries=%d attempt=%d/%d body=%s caller=%s",
                    self._path_stub(path), method.upper(), retries, attempt + 1, retries + 1, body[:160], caller or "-",
                )
                raise FyersWAFError(
                    f"Fyers/Cloudflare WAF blocked request to {self._path_stub(path)} (HTTP 403): {body[:120]}"
                )

            if status in (429, 1015):
                st.rate_limited += 1
                if attempt >= retries:
                    st.failures += 1
                    logger.warning(
                        "fyers.retry endpoint=%s method=%s status=%d retries=%d attempts_exhausted=1 caller=%s",
                        self._path_stub(path), method.upper(), status, retries, caller or "-",
                    )
                    return FyersResponse(status_code=status, body=getattr(resp, "content", b""), headers=dict(getattr(resp, "headers", {}))), attempt, total_wait
                delay = self._retry_after(resp) or self._backoff(attempt, st, reason=f"http-{status}")
                total_wait += delay
                await asyncio.sleep(delay)
                attempt += 1
                st.retries += 1
                logger.info(
                    "fyers.retry endpoint=%s method=%s status=%d retries=%d attempt=%d/%d delay=%.2fs caller=%s",
                    self._path_stub(path), method.upper(), status, retries, attempt, retries + 1, delay, caller or "-",
                )
                continue

            if status in RETRYABLE_HTTP or status >= 500:
                if attempt >= retries:
                    st.failures += 1
                    logger.warning(
                        "fyers.retry endpoint=%s method=%s status=%d retries=%d attempts_exhausted=1 caller=%s",
                        self._path_stub(path), method.upper(), status, retries, caller or "-",
                    )
                    return FyersResponse(status_code=status, body=getattr(resp, "content", b""), headers=dict(getattr(resp, "headers", {}))), attempt, total_wait
                delay = self._backoff(attempt, st, reason=f"http-{status}")
                total_wait += delay
                await asyncio.sleep(delay)
                attempt += 1
                st.retries += 1
                logger.info(
                    "fyers.retry endpoint=%s method=%s status=%d retries=%d attempt=%d/%d delay=%.2fs caller=%s",
                    self._path_stub(path), method.upper(), status, retries, attempt, retries + 1, delay, caller or "-",
                )
                continue

            return FyersResponse(
                status_code=status,
                body=getattr(resp, "content", b"") or getattr(resp, "body", b"") or resp.text.encode("utf-8", "replace"),
                headers=dict(getattr(resp, "headers", {}) or {}),
            ), attempt, total_wait

    # -- helpers ------------------------------------------------------------

    def _backoff(self, attempt: int, st: EndpointStats, reason: str) -> float:
        """Exponential backoff with full jitter: delay in [0, base*2**attempt]."""
        cap = min(BACKOFF_BASE_SECONDS * (2 ** attempt), BACKOFF_CAP_SECONDS)
        return random.uniform(0.0, cap)

    @staticmethod
    def _retry_after(resp) -> float | None:
        try:
            headers = getattr(resp, "headers", {}) or {}
            raw = headers.get("Retry-After") or headers.get("retry-after")
            if raw:
                return float(raw)
        except (TypeError, ValueError):
            pass
        return None

    @staticmethod
    def _path_stub(url: str) -> str:
        if url.startswith("https://public.fyers.in/"):
            return url.split("sym_details/")[-1].split("?")[0]
        return url.split("?")[0].split("api-t1.fyers.in")[-1].split("api.fyers.in")[-1] or url

    @staticmethod
    def _cache_key(method: str, path: str, json_body: dict | None, params: dict | None) -> str:
        raw = f"{method.upper()} {path} {json.dumps(json_body or {}, sort_keys=True) if json_body else ''} {json.dumps(params or {}, sort_keys=True) if params else ''}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# Registry: one transport per access token (client_id), shared process-wide so
# rate accounting is global per token regardless of how many adapter instances
# or callers exist.
_transports: dict[str, FyersTransport] = {}
_limiters: dict[str, TokenRateLimiter] = {}


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
