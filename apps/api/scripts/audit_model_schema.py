"""Report pydantic models against the live schema: fields the code writes but the DB lacks.

Finds the class of gap where a model declares a column, production has it because somebody
added it by hand, and no migration ever captured it. The symptom is always the same and always
misleading: PostgREST answers `PGRST204`/`42703`, `async_safe_single` swallows it, and the
caller reads "nothing here" rather than "the schema is wrong".

`profiles.phone` was found this way — declared on `UserProfile`, present in production, and
created by no migration in the directory. `profiles.onboarding_completed` was the same story
with a migration that existed but had not been applied locally.

Only checks models whose table name can be derived, and reports rather than changes anything.
Applying a missing column is a judgement call about intent, so this prints the gap and stops.

Run:  python scripts/audit_model_schema.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

CONTAINER = "supabase_db_trademetrix-terminal"

# Models whose table is not just the class name lowercased, or that wrap something else.
TABLE_OVERRIDES = {
    "UserProfile": "profiles",
    "StrategySpec": None,          # not a DB row
    "RuntimeRecord": None,
    "OmniOrder": "oms_orders",
    "BracketOrder": "oms_bracket_orders",
    "OCOOrder": "oms_oco_orders",
    "BrokerCredential": "broker_credentials",
    "AdminAuditEntry": None,
    "PaperAccount": None,          # engine state, not a table
    "PaperPosition": None,
    "PaperFill": None,
    "PaperTrade": None,
}

FIELD_RE = re.compile(r"^\s{4}(\w+)\s*:\s*[^=]+=", re.M)


def db_columns(table: str) -> set[str] | None:
    proc = subprocess.run(
        ["docker", "exec", CONTAINER, "psql", "-U", "postgres", "-d", "postgres", "-tAc",
         f"SELECT column_name FROM information_schema.columns "
         f"WHERE table_schema='public' AND table_name='{table}';"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return None
    out = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    return out or None


def db_tables() -> set[str]:
    proc = subprocess.run(
        ["docker", "exec", CONTAINER, "psql", "-U", "postgres", "-d", "postgres", "-tAc",
         "SELECT table_name FROM information_schema.tables "
         "WHERE table_schema='public' AND table_type='BASE TABLE';"],
        capture_output=True, text=True,
    )
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def model_classes() -> list[tuple[str, str, list[str]]]:
    """(source file, class name, field names) for every pydantic model in core/models.py."""
    src = (API_ROOT / "core" / "models.py").read_text()
    out: list[tuple[str, str, list[str]]] = []
    for match in re.finditer(r"^class (\w+)\(([^)]*BaseModel[^)]*)\):", src, re.M):
        name = match.group(1)
        body_start = match.end()
        nxt = re.search(r"^class \w+", src[body_start:], re.M)
        body = src[body_start: body_start + (nxt.start() if nxt else len(src))]
        fields = FIELD_RE.findall(body)
        if fields:
            out.append(("core/models.py", name, fields))
    return out


def main() -> int:
    tables = db_tables()
    if not tables:
        print("no local database reachable — start the local Supabase stack first")
        return 2

    print(f"local database: {len(tables)} public tables\n")
    gaps: list[tuple[str, str, list[str]]] = []
    skipped = 0

    for source, cls, fields in model_classes():
        table = TABLE_OVERRIDES.get(cls, cls.lower())
        if table is None:
            skipped += 1
            continue
        if table not in tables:
            # The table may legitimately live under another name, or not exist locally at all.
            print(f"  ? {cls:<26} table {table!r} not present locally — skipped")
            skipped += 1
            continue
        have = db_columns(table)
        if not have:
            continue
        # A model that mirrors a row will carry the row's own columns; compare only the ones
        # the model declares, and ignore Python-side helpers such as `model_config`.
        missing = [f for f in fields if f not in have]
        if missing:
            gaps.append((table, cls, missing))
            print(f"  GAP  {table}.{cls}")
            print(f"        model declares : {', '.join(missing)}")
            print(f"        table has      : {', '.join(sorted(have))}")

    print()
    if not gaps:
        print("no gaps: every model field has a matching column")
        return 0
    print(f"{len(gaps)} model(s) declare columns the local schema does not have "
          f"({skipped} skipped)")
    print("\nA column here is not automatically a bug — a model may be describing a future or "
          "remote\ntable. But each one is a place where a write would fail silently and read as "
          "'empty'.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
