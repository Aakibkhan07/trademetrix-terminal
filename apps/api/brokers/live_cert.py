"""Live broker certification CLI (SDK v2 Phase 4).

Runs the live certification flow against a connected broker adapter and writes
``.json`` + ``.md`` reports. Order lifecycle steps are gated behind
``--allow-orders``.

Typical use (on the API host, with valid credentials present):

    python -m brokers.live_cert --broker fyers --out docs/evolve_certs/fyers_live.json

The runner resolves the configured broker adapter for the given name and calls
:func:`brokers.sdk.live_cert.run_live_certification`.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

logger = logging.getLogger("brokers.live_cert")


def _load_adapter(broker: str):
    """Instantiate the broker adapter (optionally with a fetched session)."""
    from brokers.sdk.registry import get_registry

    reg = get_registry()
    if broker not in reg:
        raise SystemExit(f"Unknown broker '{broker}'. Available: {', '.join(reg.names())}")
    adapter = reg.create(broker, wrap_circuit_breaker=False)
    return adapter


async def _run(broker: str, allow_orders: bool, out_path: str) -> None:
    from brokers.sdk.live_cert import run_live_certification, write_report

    adapter = _load_adapter(broker)
    result = await run_live_certification(adapter, broker=broker, allow_orders=allow_orders)
    write_report(result, out_path)
    print(result.to_dict()["result"], f"-> {out_path} (+ .md)")
    for step in result.steps.values():
        status = "SKIP" if step.get("skipped") else ("PASS" if step.get("passed") else "FAIL")
        print(f"  {status:4} {step['check']:<16} {step.get('error') or step.get('detail') or ''}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Live broker certification")
    parser.add_argument("--broker", required=True, help="Broker key (registered in the SDK registry)")
    parser.add_argument("--out", default="/tmp/live_certification.json", help="Output report path (.json)")
    parser.add_argument("--allow-orders", action="store_true", help="Run place/modify/cancel lifecycle steps")
    args = parser.parse_args(argv)
    asyncio.run(_run(args.broker, args.allow_orders, args.out))


if __name__ == "__main__":
    main(sys.argv[1:])