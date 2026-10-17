"""Has production's `orders` table ever held two rows for one fill?

The only claim in this fix that was not measured locally. Everything else was reproduced with a
fake `orders` table; this one needs the real one, because it is a question about what the table
actually accumulated.

Read-only. Needs `SUPABASE_URL` + a service key in the environment, or run inside the API
container where both are present. Fails loudly rather than reporting "clean" when it cannot
connect -- a check that cannot reach the database must not be mistaken for one that found
nothing.

Run from `apps/api`:

    .venv/bin/python scripts/check_production_duplicate_fills.py
"""
import os
import sys
from collections import Counter


def main() -> int:
    try:
        from supabase import create_client
    except ImportError:
        print("  supabase-py is not installed in this interpreter", file=sys.stderr)
        return 2

    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        print("  SUPABASE_URL / SUPABASE_SERVICE_KEY are not set -- cannot reach the database.\n"
              "  This check NEEDS a real database. It has never been run.", file=sys.stderr)
        return 2
    if "localhost" in url:
        print(f"  SUPABASE_URL is {url} -- that is the LOCAL database, not production.\n"
              "  Answering for production requires the production URL.", file=sys.stderr)
        return 2

    sb = create_client(url, key)

    print(f"  querying {url}")
    rows = (
        sb.table("orders")
        .select("user_id,broker_order_id,client_order_id,filled_quantity,average_price,created_at")
        .eq("broker", "paper")
        .eq("status", "FILLED")
        .limit(20000)
        .execute()
        .data
    ) or []

    print(f"  {len(rows)} FILLED paper rows examined")
    if not rows:
        print("  no paper fills at all -- nothing to reconcile")
        return 0

    def key(r):
        return (r.get("user_id"), r.get("broker_order_id"), r.get("filled_quantity"),
                r.get("average_price"))

    counts = Counter(key(r) for r in rows)
    dupes = {k: v for k, v in counts.items() if v > 1}

    by_user = Counter(k[0] for k in dupes)
    print()
    print(f"  duplicate fill groups : {len(dupes)}")
    if dupes:
        print(f"  affected users        : {len(by_user)}")
        for user, n in by_user.most_common(10):
            print(f"    {user}  {n} duplicated fills")
        print()
        print("  a sample (user, broker_order_id, filled_qty, avg_price, rows):")
        for k, v in list(dupes.items())[:10]:
            print(f"    {k[0]}  {k[1]}  qty={k[2]}  px={k[3]}  x{v}")
        print()
        print("  These are the rows the restore would have replayed twice.")
        return 1

    print()
    print("  no duplicate fills: the audit table holds one row per fill.")
    print("  So the doubling is NOT explained by duplicate rows -- see the docstring on")
    print("  PaperBroker._restore_positions for what was actually measured instead.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())