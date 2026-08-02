"""Generic broker HTTP transport with pluggable strategy classes.

Owns the shared plumbing every broker REST client needs, with zero
broker-specific logic in this module:

- **Rate limiting** — per-token sliding-window limiter (sustained RPM + burst)
  via the pluggable :class:`RateLimiter` strategy.
- **Retries** — honor ``Retry-After`` when present, else jittered exponential
  backoff (:class:`RetryPolicy`); net errors and retryable statuses retried,
  WAF blocks never.
- **Deduplication** — concurrent identical requests await one round-trip.
- **Static caching** — per-endpoint ``cache_ttl`` for GET responses.
- **Pluggable strategies** — auth/signing (:class:`AuthStrategy`), request
  headers (:class:`HeaderStrategy`), URL building (:class:`URLBuilder`),
  response parsing (:class:`ResponseParser`), error translation
  (:class:`ErrorTranslator`), retry policy (:class:`RetryPolicy`), rate-limit
  policy (:class:`RateLimiter`).
- **Observability** — structured ``<prefix>.request`` / ``<prefix>.retry``
  logs, correlation ids, per-endpoint RPM accounting via ``snapshot()`` /
  ``health()``, and Prometheus counters when ``metrics_enabled``.

Adding a broker = provide a :class:`TransportConfig` plus strategy overrides.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx

from brokers.sdk.errors import BrokerWAFError

logger = logging.getLogger("brokers.sdk.transport")

DEFAULT_BACKOFF_BASE_SECONDS = 0.25
DEFAULT_BACKOFF_CAP_SECONDS = 8.0
DEFAULT_MAX_RETRIES = 3

# Retryable HTTP statuses: rate limiting (429, 1015) and transient 5xx.
RETRYABLE_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504, 521, 1015})
# Statuses treated as broker/edge rate limiting (Retry-After aware).
RATE_LIMIT_STATUSES = frozenset({429, 1015})
# Statuses treated as a CDN WAF block — never retried.
WAF_STATUSES = frozenset({403})
# Retryable transport errors (network blips, timeouts, resets).
RETRYABLE_NET = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    httpx.ReadError,
    httpx.TransportError,
)


@dataclass
class TransportConfig:
    """Per-broker knobs for the generic transport."""

    broker: str = "generic"
    base_url: str = ""
    rpm: int = 100
    burst: int = 8
    window_seconds: float = 60.0
    backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS
    backoff_cap_seconds: float = DEFAULT_BACKOFF_CAP_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    timeout_seconds: float = 30.0
    impersonate: str | None = None  # curl_cffi browser fingerprint (e.g. "chrome131")
    retryable_http: frozenset = field(default_factory=lambda: frozenset(RETRYABLE_HTTP_STATUSES))
    rate_limit_statuses: frozenset = field(default_factory=lambda: frozenset(RATE_LIMIT_STATUSES))
    waf_statuses: frozenset = field(default_factory=lambda: frozenset(WAF_STATUSES))
    log_prefix: str = "broker"
    metrics_enabled: bool = True
    cache_max_entries: int = 1024


class TransportResponse:
    """Minimal httpx-like response so existing parsers keep working."""

    def __init__(self, status_code: int, body: bytes, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self.body = body
        self.headers = headers or {}

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


class RateLimiter:
    """Sliding-window rate limiter for one broker token (the rate-limit policy).

    Enforces both the sustained RPM budget and a per-second burst ceiling.
    ``acquire()`` sleeps until a slot frees up (never fails, never tight-loops).
    """

    def __init__(self, key: str, rpm: int = 100, burst: int = 8, window_seconds: float = 60.0):
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


# Legacy alias — retained so existing broker code keeps its original name.
TokenRateLimiter = RateLimiter


@dataclass
class EndpointStats:
    """Rolling 60s accounting for one endpoint (path only)."""

    path: str
    calls: int = 0              # logical calls (incl. cache/dedup hits)
    wire_calls: int = 0         # actual HTTP round-trips
    cache_hits: int = 0
    dedup_hits: int = 0
    retries: int = 0            # total retry attempts (all reasons)
    rate_limited: int = 0       # 429/1015 responses seen
    waf_blocked: int = 0        # WAF blocks seen
    failures: int = 0           # final failures (non-2xx after retries)
    latency_ms: float = 0.0     # cumulative wire latency (retries excluded)
    latency_count: int = 0
    first_seen: float = field(default_factory=time.monotonic)
    last_seen: float = field(default_factory=time.monotonic)

    def rpm(self) -> float:
        elapsed = max(self.last_seen - self.first_seen, 1.0)
        return round(self.calls / elapsed * 60.0, 1)


# ---------------------------------------------------------------------------
# Strategy extension points — brokers override these; the transport never
# branches on broker identity.
# ---------------------------------------------------------------------------


class AuthStrategy:
    """Authentication header + request-signing strategy.

    ``authorization()`` returns the header value (or None when unauthenticated);
    ``sign()`` is a hook for brokers that sign requests (HMAC etc.).
    """

    def authorization(self, client_id: str, access_token: str) -> str | None:
        if not access_token:
            return None
        return f"Bearer {access_token}"

    def sign(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        json_body: dict | None,
        params: dict | None,
        client_id: str,
        access_token: str,
    ) -> None:
        pass


class HeaderStrategy:
    """Builds per-request headers (static set + content type logic)."""

    def __init__(self, static_headers: dict[str, str] | None = None):
        base = {"Accept": "application/json, text/plain, */*"}
        base.update(static_headers or {})
        self.static_headers = base

    def build(self, method: str, json_body: dict | None) -> dict[str, str]:
        headers = dict(self.static_headers)
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        return headers


class URLBuilder:
    """Maps request paths onto absolute URLs and produces stats stubs."""

    def __init__(self, base_url: str = ""):
        self.base_url = base_url

    def build(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return f"{self.base_url}{path}" if self.base_url else path

    def stub(self, url: str) -> str:
        """Short stable identity for stats/logs — the URL path."""
        return urlsplit(url).path or url


class ResponseParser:
    """Normalizes a raw client response into :class:`TransportResponse`."""

    def parse(self, raw: Any) -> TransportResponse:
        body = (
            getattr(raw, "content", b"")
            or getattr(raw, "body", b"")
            or getattr(raw, "text", "").encode("utf-8", "replace")
        )
        return TransportResponse(
            status_code=getattr(raw, "status_code", 0),
            body=body,
            headers=dict(getattr(raw, "headers", {}) or {}),
        )


class ErrorTranslator:
    """Maps non-2xx statuses onto typed BrokerError subclasses.

    Returning an exception raises it immediately (no retry) — used for WAF
    blocks; returning None falls through to the retry policy / raw response.
    """

    def translate(self, status: int, raw: Any, path_stub: str, broker: str = "") -> Exception | None:
        if status in WAF_STATUSES:
            body = getattr(raw, "text", "")[:300]
            return BrokerWAFError(
                f"{broker or 'Broker'} endpoint blocked by CDN WAF (HTTP {status}) for {path_stub}: {body[:120]}",
                broker=broker,
            )
        return None


class RetryPolicy:
    """Retry policy: which statuses/errors retry, how long to wait."""

    def __init__(self, config: TransportConfig):
        self.config = config

    def is_rate_limit(self, status: int) -> bool:
        return status in self.config.rate_limit_statuses

    def retryable_status(self, status: int) -> bool:
        return status in self.config.retryable_http or status >= 500

    def retry_after(self, raw: Any) -> float | None:
        try:
            headers = getattr(raw, "headers", {}) or {}
            raw_value = headers.get("Retry-After") or headers.get("retry-after")
            if raw_value:
                return float(raw_value)
        except (TypeError, ValueError):
            pass
        return None

    def backoff(self, attempt: int) -> float:
        """Exponential backoff with full jitter: delay in [0, base*2**attempt]."""
        cap = min(self.config.backoff_base_seconds * (2 ** attempt), self.config.backoff_cap_seconds)
        return random.uniform(0.0, cap)


# ---------------------------------------------------------------------------
# The transport itself.
# ---------------------------------------------------------------------------


class HttpTransport:
    """Rate-limited, retrying, deduplicating, caching broker HTTP transport.

    One instance per token/credential so that all adapter/caller instances for
    the same token share one limiter, one connection pool and one RPM ledger.
    """

    def __init__(
        self,
        config: TransportConfig | None = None,
        *,
        client_id: str = "",
        access_token: str = "",
        limiter: RateLimiter | None = None,
        auth: AuthStrategy | None = None,
        headers: HeaderStrategy | None = None,
        url_builder: URLBuilder | None = None,
        parser: ResponseParser | None = None,
        translator: ErrorTranslator | None = None,
        retry: RetryPolicy | None = None,
    ):
        self.config = config or TransportConfig()
        self.client_id = client_id
        self.access_token = access_token
        self._limiter = limiter or RateLimiter(
            client_id or "anon",
            rpm=self.config.rpm,
            burst=self.config.burst,
            window_seconds=self.config.window_seconds,
        )
        self._auth = auth or AuthStrategy()
        self._headers = headers or HeaderStrategy()
        self._url_builder = url_builder or URLBuilder(self.config.base_url)
        self._parser = parser or ResponseParser()
        self._translator = translator or ErrorTranslator()
        self._retry = retry or RetryPolicy(self.config)
        self._client: Any = None
        self._cache: dict[str, tuple[float, TransportResponse]] = {}
        self._inflight: dict[str, asyncio.Future] = {}
        self._stats: dict[str, EndpointStats] = {}
        self._lock = asyncio.Lock()
        self._last_error = ""

    # -- shared client ------------------------------------------------------

    async def _get_client(self) -> Any:
        if self._client is None:
            if self.config.impersonate:
                from curl_cffi.requests import AsyncSession

                self._client = AsyncSession(
                    impersonate=self.config.impersonate, timeout=self.config.timeout_seconds
                )
            else:
                self._client = httpx.AsyncClient(timeout=self.config.timeout_seconds)
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

    def health(self) -> dict[str, Any]:
        """Liveness/diagnostic summary (metrics + admin use)."""
        latencies = [st for st in self._stats.values() if st.latency_count]
        avg_ms = (
            round(sum(st.latency_ms for st in latencies) / sum(st.latency_count for st in latencies), 1)
            if latencies
            else 0.0
        )
        return {
            "ok": True,
            "broker": self.config.broker,
            "token": self.client_id or "anon",
            "rate_limit": {
                "budget_rpm": self._limiter.rpm,
                "burst_per_second": self._limiter.burst,
                "used_last_minute": self._limiter.pending_in_window(60),
            },
            "endpoints_active": len(self._stats),
            "last_error": self._last_error or None,
            "avg_latency_ms": avg_ms,
        }

    # -- metrics ------------------------------------------------------------

    def _emit(self, name: str, endpoint: str) -> None:
        if not self.config.metrics_enabled:
            return
        try:
            from core.prometheus import record_broker_transport_metric

            record_broker_transport_metric(name, self.config.broker, endpoint)
        except Exception:
            pass

    def _emit_latency(self, endpoint: str, seconds: float) -> None:
        if not self.config.metrics_enabled:
            return
        try:
            from core.prometheus import record_broker_transport_latency

            record_broker_transport_latency(self.config.broker, endpoint, seconds)
        except Exception:
            pass

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
        retries: int | None = None,
        caller: str = "",
        authenticated: bool = True,
        correlation_id: str = "",
    ) -> TransportResponse:
        """Execute one broker API call with rate limiting, retry, dedup, cache.

        ``path`` is a full URL or a path under the configured base host.
        ``cache_ttl > 0`` (GET only) caches successful 2xx bodies.
        ``dedup`` collapses concurrent identical requests into one round-trip.
        ``retries=None`` uses the config default (usually 3; order writes pass 0).
        WAF blocks raise ``BrokerWAFError`` (or the broker's subclass);
        otherwise the final response is returned.
        """
        if retries is None:
            retries = self.config.max_retries

        url = self._url_builder.build(path)
        path_stub = self._url_builder.stub(url)
        st = self._stats_for(path_stub)
        st.calls += 1
        self._emit("calls", path_stub)

        corr = correlation_id or uuid.uuid4().hex[:12]
        cache_key = self._cache_key(method, url, json_body, params)
        if method.upper() == "GET" and cache_ttl > 0:
            cached = self._cache.get(cache_key)
            if cached and cached[0] > time.monotonic():
                st.cache_hits += 1
                self._emit("cache_hits", path_stub)
                logger.info(
                    "%s.request endpoint=%s method=%s status=%s retries=%d latency_ms=0.0 cached=1 dedup=0 rate_rpm=%.1f caller=%s corr=%s",
                    self.config.log_prefix, path_stub, method.upper(), cached[1].status_code, 0, st.rpm(), caller or "-", corr,
                )
                return cached[1]

        if dedup:
            existing = self._inflight.get(cache_key)
            if existing is not None:
                try:
                    resp = await asyncio.shield(existing)
                    st.dedup_hits += 1
                    self._emit("dedup_hits", path_stub)
                    logger.info(
                        "%s.request endpoint=%s method=%s status=%s retries=%d latency_ms=0.0 cached=0 dedup=1 rate_rpm=%.1f caller=%s corr=%s",
                        self.config.log_prefix, path_stub, method.upper(), resp.status_code, 0, st.rpm(), caller or "-", corr,
                    )
                    return resp
                except Exception:
                    pass  # fell through — retry path below lost the race

        if dedup:
            future: asyncio.Future = asyncio.get_running_loop().create_future()
            self._inflight[cache_key] = future
        try:
            resp, retry_count, wait_sum = await self._execute_with_retries(
                method, url, json_body, params, retries, st, caller, authenticated, corr
            )
            if method.upper() == "GET" and cache_ttl > 0 and resp.status_code < 400:
                self._cache[cache_key] = (time.monotonic() + cache_ttl, resp)
                while len(self._cache) > self.config.cache_max_entries:
                    self._cache.pop(next(iter(self._cache)), None)
            self._emit_latency(path_stub, wait_sum)
            logger.info(
                "%s.request endpoint=%s method=%s status=%d retries=%d latency_ms=%.1f cached=0 dedup=0 rate_rpm=%.1f caller=%s corr=%s",
                self.config.log_prefix, path_stub, method.upper(), resp.status_code, retry_count, wait_sum * 1000, st.rpm(), caller or "-", corr,
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
        url: str,
        json_body: dict | None,
        params: dict | None,
        retries: int,
        st: EndpointStats,
        caller: str,
        authenticated: bool,
        corr: str,
    ):
        client = await self._get_client()
        headers = self._headers.build(method, json_body)
        if authenticated:
            auth_value = self._auth.authorization(self.client_id, self.access_token)
            if auth_value:
                headers["Authorization"] = auth_value

        attempt = 0
        total_wait = 0.0
        prefix = self.config.log_prefix
        stub = self._url_builder.stub(url)
        while True:
            await self._limiter.acquire()
            started = time.monotonic()
            self._auth.sign(method, url, headers, json_body, params, self.client_id, self.access_token)
            try:
                if method.upper() == "GET":
                    resp = await client.get(url, params=params, headers=headers)
                elif method.upper() == "DELETE":
                    resp = await client.delete(url, json=json_body, headers=headers)
                else:
                    resp = await client.post(url, json=json_body, headers=headers) if method.upper() == "POST" else await client.patch(url, json=json_body, headers=headers)
            except RETRYABLE_NET as e:
                st.wire_calls += 1
                self._emit("wire_calls", stub)
                if attempt >= retries:
                    st.failures += 1
                    self._emit("failures", stub)
                    self._last_error = f"transport {type(e).__name__}"
                    logger.warning(
                        "%s.retry endpoint=%s method=%s error=transport retries=%d attempt=%d/%d caller=%s corr=%s",
                        prefix, stub, method.upper(), retries, attempt + 1, retries + 1, caller or "-", corr,
                    )
                    raise
                delay = self._retry.backoff(attempt)
                total_wait += delay
                await asyncio.sleep(delay)
                attempt += 1
                st.retries += 1
                self._emit("retries", stub)
                logger.info(
                    "%s.retry endpoint=%s method=%s status=transport-error retries=%d attempt=%d/%d delay=%.2fs caller=%s corr=%s",
                    prefix, stub, method.upper(), retries, attempt, retries + 1, delay, caller or "-", corr,
                )
                continue

            st.wire_calls += 1
            self._emit("wire_calls", stub)
            st.latency_ms += (time.monotonic() - started) * 1000
            st.latency_count += 1
            status = resp.status_code

            if status in self.config.waf_statuses:
                err = self._translator.translate(status, resp, stub, broker=self.config.broker)
                if err is not None:
                    st.waf_blocked += 1
                    self._emit("waf_blocks", stub)
                    self._last_error = str(err)
                    body = getattr(resp, "text", "")[:300]
                    logger.error(
                        "%s.waf endpoint=%s method=%s status=%d retries=%d attempt=%d/%d body=%s caller=%s corr=%s",
                        prefix, stub, method.upper(), status, retries, attempt + 1, retries + 1, body[:160], caller or "-", corr,
                    )
                    raise err

            if self._retry.is_rate_limit(status):
                st.rate_limited += 1
                self._emit("rate_limited", stub)
                self._last_error = f"rate-limited status={status}"
                if attempt >= retries:
                    st.failures += 1
                    self._emit("failures", stub)
                    logger.warning(
                        "%s.retry endpoint=%s method=%s status=%d retries=%d attempts_exhausted=1 caller=%s corr=%s",
                        prefix, stub, method.upper(), status, retries, caller or "-", corr,
                    )
                    return self._parser.parse(resp), attempt, total_wait
                delay = self._retry.retry_after(resp) or self._retry.backoff(attempt)
                total_wait += delay
                await asyncio.sleep(delay)
                attempt += 1
                st.retries += 1
                self._emit("retries", stub)
                logger.info(
                    "%s.retry endpoint=%s method=%s status=%d retries=%d attempt=%d/%d delay=%.2fs caller=%s corr=%s",
                    prefix, stub, method.upper(), status, retries, attempt, retries + 1, delay, caller or "-", corr,
                )
                continue

            if self._retry.retryable_status(status):
                if attempt >= retries:
                    st.failures += 1
                    self._emit("failures", stub)
                    self._last_error = f"status={status} attempts exhausted"
                    logger.warning(
                        "%s.retry endpoint=%s method=%s status=%d retries=%d attempts_exhausted=1 caller=%s corr=%s",
                        prefix, stub, method.upper(), status, retries, caller or "-", corr,
                    )
                    return self._parser.parse(resp), attempt, total_wait
                delay = self._retry.backoff(attempt)
                total_wait += delay
                await asyncio.sleep(delay)
                attempt += 1
                st.retries += 1
                self._emit("retries", stub)
                logger.info(
                    "%s.retry endpoint=%s method=%s status=%d retries=%d attempt=%d/%d delay=%.2fs caller=%s corr=%s",
                    prefix, stub, method.upper(), status, retries, attempt, retries + 1, delay, caller or "-", corr,
                )
                continue

            return self._parser.parse(resp), attempt, total_wait

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _cache_key(method: str, path: str, json_body: dict | None, params: dict | None) -> str:
        raw = f"{method.upper()} {path} {json.dumps(json_body or {}, sort_keys=True) if json_body else ''} {json.dumps(params or {}, sort_keys=True) if params else ''}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
