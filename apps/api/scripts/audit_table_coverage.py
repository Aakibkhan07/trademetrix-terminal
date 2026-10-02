"""Report tables the API reads or writes that the schema does not have, and whether a migration creates them.

Found eight such tables in this codebase. Every one existed in production because it was created
there by hand, and none of it reached a migration, so a fresh environment built from this repository
cannot start.

The failure is silent rather than loud, which is what made it survive. Every query goes through
`core.safe_query`, whose `async_safe_single` / `async_safe_execute` catch all exceptions and return
`None` / `[]`. A caller therefore reads "no rows" where the truth is "no table", and PostgREST's
`PGRST205` sits in the log where nothing looks for it.

`/alerts` is the clearest case: `POST /api/v1/alerts/` returned **500** because `user_alerts` did not
exist, and the alerts page showed an empty list — indistinguishable from a user who has set none.
Creating an alert through the product's own endpoint is what surfaced it; loading the page never
would have.

For each missing table this also reports whether any migration in `supabase/migrations/` mentions it,
which separates the two cases that need different fixes:

  * a migration exists but was never applied — a deployment problem
  * no migration mentions it — the schema was hand-edited and never captured

Reports only; it changes nothing.

    python scripts/audit_table_coverage.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# scripts/audit_table_coverage.py -> scripts -> api -> apps -> repo root
API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]
MIGRATIONS = REPO_ROOT / "supabase" / "migrations"
CONTAINER = "supabase_db_trademetrix-terminal"

# `supabase.table("x")` and `.table('x')`, including the `_sb()` and `get_supabase()` variants —
# all of them reach the same place, so the call name deliberately does not matter here.
TABLE_REF_RE = re.compile(r"""\.table\(\s*["'](\w+)["']""")
SQL_LINE_COMMENT = re.compile(r"--[^\n]*")
SQL_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def strip_sql_comments(sql: str) -> str:
    """Remove SQL comments, keeping string literals intact.

    Necessary because "does a migration mention this table" has to mean *creates it*, not *talks
    about it*. The migration that documents the missing-tables problem explains in prose why
    `backtest_results` is deliberately not created — and a plain substring search read that
    explanation as a migration for it, classifying a table nobody creates as merely unapplied. A
    tool that cannot tell a comment from a statement cannot be trusted about schema.
    """
    return SQL_BLOCK_COMMENT.sub(" ", SQL_LINE_COMMENT.sub(" ", sql))


def code_table_references() -> dict[str, set[str]]:
    """`{table: {files that touch it}}` across the API, excluding the virtualenv."""
    out: dict[str, set[str]] = {}
    for f in sorted(API_ROOT.rglob("*.py")):
        if ".venv" in f.parts or "alembic" in f.parts:
            continue
        # Skip the audit scripts themselves. This file contains the table-reference pattern as a
        # literal, so without this it reports a phantom table named after whatever the regex in
        # its own source happens to match — the first run claimed a table `x` did not exist.
        if "scripts" in f.parts and "audit_" in f.name:
            continue
        try:
            src = f.read_text()
        except UnicodeDecodeError:
            continue
        for m in TABLE_REF_RE.finditer(src):
            out.setdefault(m.group(1), set()).add(str(f.relative_to(REPO_ROOT)))
    return out


def live_tables() -> set[str]:
    """Tables and views present in the local database."""
    proc = subprocess.run(
        ["docker", "exec", CONTAINER, "psql", "-U", "postgres", "-d", "postgres", "-tAc",
         "SELECT table_name FROM information_schema.tables "
         "WHERE table_schema='public' AND table_type IN ('BASE TABLE','VIEW') ORDER BY 1;"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print(f"could not query the local database ({CONTAINER}):\n{proc.stderr.strip()}")
        raise SystemExit(2)
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def migration_files_creating(table: str) -> list[str]:
    """Migrations whose **statements** reference `table`.

    Comments are stripped first, and the match must sit next to a DDL verb or a constraint clause,
    so prose about a table does not count as creating it.
    """
    pattern = re.compile(
        r"(?:CREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|VIEW|MATERIALIZED\s+VIEW)"
        r"|ALTER\s+TABLE|DROP\s+(?:TABLE|VIEW)|INSERT\s+INTO|UPDATE|DELETE\s+FROM|FROM|JOIN)"
        r"\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:ONLY\s+)?"
        r"(?:public\.)?"
        + re.escape(table)
        + r"\b",
        re.I,
    )
    hits = []
    for f in sorted(MIGRATIONS.glob("*.sql")):
        try:
            sql = strip_sql_comments(f.read_text())
        except UnicodeDecodeError:
            continue
        if pattern.search(sql) or re.search(
            r"\b" + re.escape(table) + r"\b\s*\(", sql, re.I
        ):
            hits.append(f.name)
    return hits


def main() -> int:
    refs = code_table_references()
    have = live_tables()

    print(f"migration directory        : {MIGRATIONS}")
    print(f"migrations in it           : {len(list(MIGRATIONS.glob('*.sql')))}")
    print(f"tables referenced in code  : {len(refs)}")
    print(f"present in the local schema: {len(have)}  (tables and views)\n")

    missing = sorted(t for t in refs if t not in have)
    if not missing:
        print("every table the code touches exists in this schema")
        print("and this schema can be reproduced by applying the migrations in order")
        return 0

    unapplied, uncaptured = [], []
    for t in missing:
        files = migration_files_creating(t)
        entry = (t, sorted(refs[t]))
        if files:
            unapplied.append((entry, files))
        else:
            uncaptured.append(entry)

    print(f"MISSING {len(missing)} table(s)\n")

    if uncaptured:
        print("── no migration CREATES them: the schema was changed by hand and never captured ──\n")
        for t, files in uncaptured:
            print(f"  {t}")
            for fp in files[:4]:
                print(f"      {fp}")
        print()

    if unapplied:
        print("── a migration creates them but was never applied to this database ──\n")
        for (t, files), migs in unapplied:
            print(f"  {t}")
            print(f"      migration: {', '.join(migs)}")
            for fp in files[:2]:
                print(f"      read by  : {fp}")
        print()

    print(f"{len(uncaptured)} table(s) would be lost rebuilding from this repository; "
          f"{len(unapplied)} more are simply unapplied here.")
    print("\nBoth are silent at runtime because core.safe_query turns any query failure into None or")
    print("an empty list, so the caller reads 'no rows' instead of 'no table'.")
    return 1


if __name__ == "__main__":
    sys.exit(main())