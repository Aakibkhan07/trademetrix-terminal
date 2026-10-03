#!/usr/bin/env python3
"""Diff a live database's `public` schema against a baseline, keeping only what the code touches.

Why this exists
---------------
Production was not built from `supabase/migrations/`. Measured on 2026-10-03, the two have drifted:
46 tables against 46 tables, but 27 columns declared in the repo are absent from production, 61
columns in production are absent from the repo, and 22 columns disagree on type. None of that is
visible from the repo, and most of it turns out to be harmless — but "most" is not a measurement,
and a future divergence in the other direction would break a query at runtime.

Why it is shaped the way it is
------------------------------
Two earlier attempts at this produced confident nonsense, and both failures are the reason for the
shape here:

1. Grepping the tree for column *names* reported 165 "missing columns", among them
   `orders.FILLED`, `strategy_runs.GRAPH` and `profiles.encrypted_access_token`. Those are enum
   *values* and other tables' columns: a chain walker ran 3000 characters past the end of its own
   statement. Column-level inference from source turned out to be unsound, so this script does not
   attempt it.

2. Grepping for `on_conflict="user_id,broker"` found one hit and nearly blocked a safe migration.
   The hit was inside a comment explaining why the key had been widened. Python's `ast` cannot see
   comments, so table usage here is read from the AST and is comment-proof by construction.

What survives is a table-level question, and that is the question worth asking: a column cannot
break a query against a table the code never queries.

Usage
-----
    PGPASSFILE=~/.pgpass python scripts/audit_production_schema.py --baseline baseline.tsv
    python scripts/audit_production_schema.py --url postgresql://... --baseline baseline.tsv

The baseline is the same `table<TAB>column<TAB>type` dump taken from a database built by replaying
`supabase/migrations/` in order. `--emit-baseline` prints one from any reachable database, so the
two can be regenerated the same way.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import pathlib
import subprocess
import sys
from collections import defaultdict

QUERY = (
    "SELECT table_name || E'\\t' || column_name || E'\\t' || data_type "
    "FROM information_schema.columns WHERE table_schema = 'public' "
    "ORDER BY table_name, column_name;"
)

# Operations where a missing column is rejected by PostgREST rather than tolerated. `select("*")`
# is absent on purpose: it asks for whatever exists and is therefore not a dependency.
BREAKING_OPS = {"insert", "update", "upsert", "select", "eq", "neq", "gt", "gte",
                "lt", "lte", "in_", "is", "like", "ilike", "filter", "order"}


def dump_schema(psql: list[str]) -> dict[str, dict[str, str]]:
    """`{table: {column: type}}` for the public schema of the database `psql` points at."""
    out = subprocess.run(psql + ["-tAc", QUERY], capture_output=True, text=True, check=True).stdout
    schema: dict[str, dict[str, str]] = defaultdict(dict)
    for line in out.splitlines():
        parts = line.strip().split("\t")
        if len(parts) == 3 and all(parts):
            schema[parts[0]][parts[1]] = parts[2]
    return dict(schema)


def tables_the_code_queries(api_root: pathlib.Path) -> dict[str, list[str]]:
    """`{table: [files]}` for every table named in a real query.

    Read from the AST, so a table mentioned only in a comment, a docstring or a string is not
    counted. That distinction is the whole point: `on_conflict="user_id,broker"` survives grep and
    does not survive the AST, and acting on the grep result would have been wrong.
    """
    hits: dict[str, list[str]] = defaultdict(list)
    for path in sorted(api_root.rglob("*.py")):
        parts = path.parts
        if ".venv" in parts or "tests" in parts or "migrations" in parts:
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        rel = str(path.relative_to(api_root))
        for node in ast.walk(tree):
            # supabase.table("orders")  /  supabase.table(TABLE)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "table" and node.args:
                    first = node.args[0]
                    name = first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None
                    if name and rel not in hits[name]:
                        hits[name].append(rel)
    return dict(hits)


def diff(live: dict[str, dict[str, str]], base: dict[str, dict[str, str]]) -> dict:
    live_tables, base_tables = set(live), set(base)
    live_only = sorted(live_tables - base_tables)
    base_only = sorted(base_tables - live_tables)
    cols_live_only: dict[str, list[str]] = defaultdict(list)
    cols_base_only: dict[str, list[str]] = defaultdict(list)
    types: dict[str, tuple[str, str]] = {}

    for table in live_tables & base_tables:
        for col in live[table].keys() - base[table].keys():
            cols_live_only[table].append(f"{col} {live[table][col]}")
        for col in base[table].keys() - live[table].keys():
            cols_base_only[table].append(f"{col} {base[table][col]}")
        for col in live[table].keys() & base[table].keys():
            if live[table][col] != base[table][col]:
                # Keyed by `table.column`. An earlier version also wrote a bare table-name key with
                # a `[None, None]` placeholder, which inflated the count by 11 and buried the 22
                # real entries — a report that overstates its own findings is worse than none.
                types[f"{table}.{col}"] = (base[table][col], live[table][col])
    return {
        "tables_live_only": live_only,
        "tables_base_only": base_only,
        "cols_live_only": {k: sorted(v) for k, v in sorted(cols_live_only.items())},
        "cols_base_only": {k: sorted(v) for k, v in sorted(cols_base_only.items())},
        "type_mismatch": {k: v for k, v in sorted(types.items()) if isinstance(k, str)},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=os.environ.get("DATABASE_URL", ""),
                    help="postgres URL of the database to inspect (or set DATABASE_URL)")
    ap.add_argument("--baseline", type=pathlib.Path,
                    help="baseline tsv from --emit-baseline, i.e. the repo-migration build")
    ap.add_argument("--emit-baseline", action="store_true",
                    help="print this database's schema in baseline format and exit")
    ap.add_argument("--api-root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1])
    ap.add_argument("--json", type=pathlib.Path, help="also write the report as json")
    args = ap.parse_args()

    if not args.url:
        ap.error("no database url: pass --url or set DATABASE_URL")

    psql = ["psql", args.url, "-X", "-q"]
    if args.emit_baseline:
        for table, cols in sorted(dump_schema(psql).items()):
            for col, typ in sorted(cols.items()):
                print(f"{table}\t{col}\t{typ}")
        return 0

    if not args.baseline or not args.baseline.exists():
        ap.error("--baseline is required (generate one with --emit-baseline)")

    base: dict[str, dict[str, str]] = defaultdict(dict)
    for line in args.baseline.read_text().splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and all(parts):
            base[parts[0]][parts[1]] = parts[2]

    live = dump_schema(psql)
    d = diff(live, dict(base))
    used = tables_the_code_queries(args.api_root)

    live_tables = set(live)
    exercised_base_only = [t for t in d["tables_base_only"] if t in used]
    exercised_cols = {t: v for t, v in d["cols_base_only"].items() if t in used}
    live_col_count = sum(len(v) for v in live.values())
    base_col_count = sum(len(v) for v in base.values())

    print(f"live tables/columns      : {len(live_tables)} / {live_col_count}")
    print(f"baseline tables/columns  : {len(base)} / {base_col_count}")
    print(f"tables the API queries   : {len(used)}")
    print()
    print(f"tables live only         : {len(d['tables_live_only'])}  {d['tables_live_only']}")
    print(f"tables baseline only     : {len(d['tables_base_only'])}")
    print(f"columns live only        : {sum(len(v) for v in d['cols_live_only'].values())}")
    print(f"columns baseline only    : {sum(len(v) for v in d['cols_base_only'].values())}")
    print(f"type mismatches          : {len(d['type_mismatch'])}")
    print()
    if exercised_cols:
        print("DIVERGENCES ON TABLES THE API QUERIES — read these before deploying:")
        for table, cols in exercised_cols.items():
            print(f"  {table}")
            for c in cols:
                print(f"      missing in live: {c}")
    else:
        print("no column divergence on any table the API queries")

    # A type difference is not cosmetic. `squareoff_config.days` is `text` in the baseline and
    # `ARRAY` in production, and the code selects it by name — that is a value-shape change, not a
    # spelling change, so it belongs in the report rather than in the summary count.
    exercised_types = {k: v for k, v in d["type_mismatch"].items() if k.split(".")[0] in used}
    if exercised_types:
        print()
        print("TYPE DIVERGENCES ON TABLES THE API QUERIES:")
        for key, (want, got) in exercised_types.items():
            print(f"  {key:<48} baseline={want:<22} live={got}")
    if exercised_base_only:
        print()
        print(f"TABLES THE API QUERIES THAT ARE ABSENT ENTIRELY: {exercised_base_only}")
    print()
    print("column-level inference from source is deliberately absent — see the module docstring")

    if args.json:
        args.json.write_text(json.dumps({**d, "exercised": used}, indent=1))
        print(f"report written: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())