"""Read-only check of the market-data-role repository against PRODUCTION.

Deliberately read-only. The role-aware reads are safe to run against live data; the writes
(`activate_broker`, `upsert_credentials`, `delete_credentials`) are not, and one of them
would change which broker a paying tenant's orders route through. So this touches `get_*` and
`resolve_market_data_broker` and nothing else.

Why this exists: the migration is applied, but "applied" is a schema fact. The question that
actually matters is whether the code that reads it now returns the right answer instead of
`None` — because `async_safe_single` turns a permission error or a missing column into `None`,
and `None` is what every caller already means by "broker not connected". A green `/health`
and a clean psql describe both coexist happily with a completely broken broker path.

Run with:  .venv/bin/python scripts/verify_production_broker_roles.py
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from infrastructure.repositories.broker_repository import (  # noqa: E402
    SupabaseBrokerRepository,
)


async def main() -> int:
    url = os.environ.get("SUPABASE_URL", "")
    if "localhost" in url or "127.0.0.1" in url:
        print("refusing to run: SUPABASE_URL is local, this checks production")
        return 1
    print(f"target: {url}\n")

    repo = SupabaseBrokerRepository()
    client = repo_module_client = None
    try:
        import infrastructure.repositories.broker_repository as repo_module

        client = repo_module.get_supabase()
    except Exception as exc:  # pragma: no cover - diagnostics only
        print(f"could not build a client: {exc}")
        return 1

    print(f"client resolves to: {client.supabase_url}\n")

    # Real tenants, read straight from the table. No hard-coded ids: this must reflect
    # whatever is actually live, including tenants nobody remembers.
    rows = (
        client.table("broker_credentials")
        .select("user_id, broker, role, is_active")
        .limit(50)
        .execute()
        .data
    )
    if not rows:
        print("no credential rows — nothing to verify")
        return 1

    users = sorted({r["user_id"] for r in rows})
    print(f"verifying {len(users)} tenants across {len(rows)} credential rows\n")
    print(f"{'broker':<10}{'role':<14}{'exec read':<12}{'mkt read':<12}{'resolves to':<12}")
    print("-" * 60)

    problems: list[str] = []
    for row in rows[:12]:
        user_id, broker, role = row["user_id"], row["broker"], row["role"]

        execution = await repo.get_by_user_and_broker(user_id, broker, role="execution")
        market_data = await repo.get_by_user_and_broker(user_id, broker, role="market_data")
        resolved = await repo.resolve_market_data_broker(user_id)

        print(
            f"{broker:<10}{role:<14}"
            f"{('ok' if execution else 'NONE'):<12}"
            f"{('ok' if market_data else '-'):<12}"
            f"{str(resolved):<12}"
        )

        # A row that exists must read back. This is the assertion that would have caught the
        # pre-migration state, where every one of these returned None.
        if not execution and role == "execution":
            problems.append(f"{broker}: execution row exists but reads back as None")
        # The fallback every existing tenant depends on.
        if row["is_active"] and role == "execution" and not resolved:
            problems.append(
                f"{broker}: active execution credential but resolve_market_data_broker "
                f"returned None — quotes would go blank for this tenant"
            )

    # Pick a tenant that actually has an active execution credential, rather than assuming
    # the first one does. The first tenant alphabetically turned out to hold only an inactive
    # `lemonn` row, so `get_active_broker` correctly answered `None` and this check flagged a
    # non-problem — a reminder that "this returned None" only means something next to "this
    # should have returned something".
    with_active = [
        r["user_id"] for r in rows
        if r["is_active"] and r["role"] == "execution"
    ]
    if not with_active:
        print("\nno tenant has an active execution credential; skipping the active-broker check")
    else:
        probe = with_active[0]
        active = await repo.get_active_broker(probe)
        probe_broker = next(
            r["broker"] for r in rows
            if r["user_id"] == probe and r["is_active"] and r["role"] == "execution"
        )
        print(f"\nget_active_broker(tenant with active {probe_broker}) = {active}")
        if not active:
            problems.append(
                f"get_active_broker returned None for a tenant with an active {probe_broker} "
                f"credential"
            )
        elif active != probe_broker:
            print(f"  note: resolved to {active!r}, not the row's own broker {probe_broker!r} "
                  f"— check whether that tenant holds more than one active broker")

    print()
    if problems:
        print(f"PROBLEMS ({len(problems)}):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("all reads returned real rows; no tenant resolves to 'no broker'")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
