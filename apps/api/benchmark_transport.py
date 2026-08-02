#!/usr/bin/env python3
"""Before/after benchmark for the generic broker transport refactor (SDK v2 Phase 2).

Runs an identical canned-client workload against the OLD ``brokers/fyers_http``
transport (git HEAD) and the NEW facade (``brokers.fyers_http`` -> generic
``brokers.sdk.transport.HttpTransport``), then reports wall latency, memory,
request counts, cache hit ratio, rate-limit utilization and retry stats.

Usage (from apps/api):
    .venv/bin/python benchmark_transport.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import tracemalloc
from unittest.mock import patch

logging.disable(logging.CRITICAL)

sys.path.insert(0, os.getcwd())

import httpx  # noqa: E402


def load_old_transport() -> object:
    """Load the pre-refactor fyers_http.py from git HEAD as a private module."""
    src = subprocess.check_output(
        ["git", "show", "HEAD:apps/api/brokers/fyers_http.py"], text=True
    )
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(src)
        path = f.name
    spec = importlib.util.spec_from_file_location("_bench_old_fyers_http", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeResp:
    def __init__(self, status: int, body: str = "{}"):
        self.status_code = status
        self.headers = {}
        self._body = body

    @property
    def text(self) -> str:
        return self._body

    @property
    def content(self) -> bytes:
        return self._body.encode()


class FakeClient:
    """Scripted client: per-path status queues, then a default."""

    def __init__(self):
        self.queues: dict[str, list[int]] = {}
        self.repeat: set[str] = set()
        self.calls: list[tuple[str, str]] = []
        self.wire = 0

    def set_queue(self, path: str, statuses: list[int], repeat: bool = False):
        self.queues[path] = list(statuses)
        if repeat:
            self.repeat.add(path)

    async def _go(self, method: str, url: str, **kw) -> FakeResp:
        self.calls.append((method, url))
        self.wire += 1
        await asyncio.sleep(0)  # yield so dedup/concurrency engages
        for path, q in self.queues.items():
            if path in url:
                if self.repeat and path in self.repeat:
                    status = q[0]
                elif q:
                    status = q.pop(0)
                else:
                    continue
                resp = FakeResp(status)
                if status in (429, 1015):
                    resp.headers["Retry-After"] = "0.05"
                return resp
        return FakeResp(200)

    get = lambda self, url, **kw: self._go("GET", url, **kw)  # noqa: E731
    post = lambda self, url, **kw: self._go("POST", url, **kw)  # noqa: E731
    patch = lambda self, url, **kw: self._go("PATCH", url, **kw)  # noqa: E731
    delete = lambda self, url, **kw: self._go("DELETE", url, **kw)  # noqa: E731


class _Noop:
    async def aclose(self):
        return None


def _make_client():
    client = FakeClient()
    client.aclose = _Noop()
    return client


async def _harness(transport) -> dict:
    delays: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(secs):
        if secs > 0:
            delays.append(secs)
        await real_sleep(min(secs, 0.001))

    lat: list[float] = []
    waf = 0

    async def timed(coro):
        t0 = time.perf_counter()
        try:
            return await coro
        except Exception:
            return None
        finally:
            lat.append((time.perf_counter() - t0) * 1000)

    with patch("asyncio.sleep", fake_sleep):
        # 100 cached GETs -> ~99% cache hit ratio after the first
        for _ in range(100):
            await timed(transport.request("GET", "/api/v3/funds", cache_ttl=5.0, caller="bench"))
        # 100 uncached GETs
        for _ in range(100):
            await timed(transport.request("GET", "/api/v3/orders", caller="bench"))
        # 8 dedup groups x 4 concurrent identical quote fetches
        for g in range(8):
            await asyncio.gather(*[
                timed(transport.request("GET", "/data/quotes", params={"symbols": f"A{g}"}, caller="bench"))
                for _ in range(4)
            ])
        # retries: every call hits 429 then succeeds; 500s then succeed
        transport._client.set_queue("/api/v3/history", [429, 200], repeat=True)
        for _ in range(6):
            await timed(transport.request("GET", "/api/v3/history", retries=3, caller="bench"))
        transport._client.set_queue("/api/v3/span-margin", [500, 500, 200], repeat=True)
        for _ in range(3):
            await timed(transport.request("GET", "/api/v3/span-margin", retries=3, caller="bench"))
        # WAF blocks (never retried)
        transport._client.set_queue("/data/denied", [403], repeat=True)
        for _ in range(2):
            try:
                await transport.request("GET", "/data/denied", retries=3, caller="bench")
            except Exception:
                waf += 1
        # 20 write calls, retries=0
        for _ in range(20):
            await timed(transport.request("POST", "/api/v3/orders/sync", json_body={"id": "x"}, retries=0, caller="bench"))

    snap = transport.snapshot()
    totals = {"calls": 0, "wire_calls": 0, "cache_hits": 0, "dedup_hits": 0,
              "retries": 0, "rate_limited": 0, "waf_blocked": 0, "failures": 0}
    for e in snap["endpoints"]:
        for k in totals:
            totals[k] += e[k]
    return {
        "wall_ms": round(sum(lat), 1),
        "requests": len(lat),
        "avg_latency_ms": round(sum(lat) / len(lat), 3),
        "p50_latency_ms": round(sorted(lat)[len(lat) // 2], 3),
        "max_latency_ms": round(max(lat), 3),
        "waf_raised": waf,
        "delays_recorded": len(delays),
        "used_last_minute": snap["used_last_minute"],
        "budget_rpm": snap["budget_rpm"],
        **totals,
    }


async def _run(label: str, transport_cls) -> dict:
    import core.prometheus  # noqa: F401  (pre-load — always resident in the API process)

    tr = transport_cls(client_id=f"bench_{label}", access_token="tok")
    tr._limiter.rpm = 100000   # disable limiting for machinery comparison
    tr._limiter.burst = 100000
    tr._client = _make_client()

    tracemalloc.start()
    results = await _harness(tr)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    results["peak_memory_kb"] = round(peak / 1024, 1)
    results["cache_hit_ratio"] = round(
        results["cache_hits"] / max(results["calls"], 1), 4
    )
    results["dedup_ratio"] = round(
        results["dedup_hits"] / max(results["calls"], 1), 4
    )
    return results


async def main() -> dict:
    old_mod = load_old_transport()
    import brokers.fyers_http as new_mod

    before = await _run("old", old_mod.FyersTransport)
    after = await _run("new", new_mod.FyersTransport)

    report = {"before": before, "after": after}
    deltas = {}
    for k in before:
        if isinstance(before[k], (int, float)):
            deltas[k] = round(after[k] - before[k], 4)
    report["deltas"] = deltas

    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    report = asyncio.run(main())
    with open(os.path.join(tempfile.gettempdir(), "transport_bench.json"), "w") as f:
        json.dump(report, f, indent=2)
    print(f"wrote {tempfile.gettempdir()}/transport_bench.json")
