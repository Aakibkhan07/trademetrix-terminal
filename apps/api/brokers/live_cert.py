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


def _resolve_credentials(broker: str, user_id: str) -> dict:
    """Load the full stored credential row for ``user_id``/``broker``.

    Uses ``get_by_user_and_broker_full`` so the decrypted-token columns are
    present; also returns the lightweight list for token_status sanity checks.
    """
    import asyncio

    from infrastructure.repositories.broker_repository import SupabaseBrokerRepository

    repo = SupabaseBrokerRepository()

    async def _load():
        # run repo's async methods in one pass
        cred = await repo.get_by_user_and_broker_full(user_id, broker)
        rows = await repo.list_credentials(user_id) or []
        return cred, rows

    cred, rows = asyncio.run(_load())
    return {"cred": cred, "rows": rows, "user_id": user_id, "broker": broker}


async def _authenticate_adapter(adapter, cred) -> None:
    """Authenticate the raw adapter using the stored credential row (decrypts token)."""
    from core.security import decrypt_broker_credentials

    client_id = (getattr(cred, "client_id", "") or "").strip()
    enc_token = getattr(cred, "encrypted_api_key", "")  # fyers client_id stored as api_key
    raw_token = ""
    try:
        raw_token = decrypt_broker_credentials(getattr(cred, "encrypted_access_token", "") or "") or ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("token decrypt failed: %s", exc)
    if not client_id:
        # fall back: api_key may hold the client_id
        try:
            client_id = decrypt_broker_credentials(enc_token) or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("api_key decrypt failed: %s", exc)
    if not raw_token or not client_id:
        raise SystemExit(
            f"Broker '{broker_name(adapter)}' has no usable access_token/client_id — re-auth required"
        )
    await adapter.authenticate({"client_id": client_id, "access_token": raw_token})


def broker_name(adapter) -> str:
    return getattr(adapter, "broker_name", "") or type(adapter).__name__


async def _run(broker: str, allow_orders: bool, out_path: str, user_id: str | None) -> None:
    from brokers.sdk.live_cert import run_live_certification, write_report

    adapter = _load_adapter(broker)
    if user_id:
        resolved = _resolve_credentials(broker, user_id)
        cred = resolved["cred"]
        if not cred:
            raise SystemExit(
                f"No stored {broker} credentials for user '{user_id}' — cannot run credential-backed cert"
            )
        await _authenticate_adapter(adapter, cred)
        logger.info(f"Authenticated {broker} adapter as {user_id}")

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
    parser.add_argument("--user", default=None, help="User UUID whose stored broker credentials to use (credential-backed run)")
    args = parser.parse_args(argv)
    asyncio.run(_run(args.broker, args.allow_orders, args.out, args.user))


if __name__ == "__main__":
    main(sys.argv[1:])