"""A strategy id must be recorded as itself, and a missing run must be said out loud.

## The bug

Two columns of vocabulary collided. `strategy_runs.strategy_id` was a `uuid NOT NULL` with a foreign
key to `strategies(id)`, but `builder/models.py` mints strategy ids as

    uuid.uuid4().hex[:12]        # '3838c1dcdc97' — 12 hex characters

which cannot be parsed as a uuid at all:

    >>> uuid.UUID('3838c1dcdc97')
    ValueError: badly formed hexadecimal UUID string

So **no Strategy Builder run could ever be recorded**, and `POST /engine/start` answered
`INTERNAL_ERROR` for an id that is perfectly valid.

## Why it was quiet

`strategy_runtime/manager.py` had a workaround, and the workaround was worse than the failure:

    try:
        sid_str = str(uuid.UUID(record.spec.strategy_id))
    except (ValueError, TypeError):
        sid_str = str(uuid.uuid4())

The coercion fails for every builder run — that is the *normal* path — so a **random uuid was
substituted** and the run row was written against a strategy that never existed. The status update
that follows filters on `.eq("strategy_id", sid_str)`, so it matched the row it had just written and
behaved as though everything were consistent.

The result is a fabricated identifier that satisfies its own lookup. Nothing downstream can detect
it, nothing is logged, and the run is unattributable afterwards: there is no way to learn which
strategy produced it. A wrong record that passes every check is more expensive than a loud failure.

`20261003_06000_strategy_runs_strategy_id_text.sql` makes the column TEXT and drops the foreign key,
so both vocabularies fit. The substitution is then not merely unnecessary but harmful — canonicalising
a builder id to a uuid would rewrite it into a different string and break the later `.eq()` match.

## The second fix

`EngineService.create_run` ended with `result.data[0]["id"]`. An insert that succeeded but returned
no representation raises `IndexError: list index out of range`, which the global handler turns into
an `INTERNAL_ERROR` that says nothing about a run not having been recorded. It now reports the
failure instead of indexing blindly.
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.services.engine_service import EngineService

# The exact shape `builder/models.py` produces.
BUILDER_ID = "3838c1dcdc97"
# A legacy catalogue id, which is a real uuid and must survive as-is.
LEGACY_ID = "00000000-0000-4000-8000-00000000d370"


def _assert_true_id_shape() -> None:
    """Pin the premise: a builder id is genuinely not a uuid."""
    with pytest.raises(ValueError):
        uuid.UUID(BUILDER_ID)
    assert len(BUILDER_ID) == 12


# ── the id must be stored as itself ──────────────────────────────────────────────

def test_a_builder_id_is_not_a_uuid():
    """The whole bug rests on this, so it is asserted rather than assumed."""
    _assert_true_id_shape()


def test_the_runtime_no_longer_substitutes_a_random_uuid():
    """The fabricated-record bug, asserted against the source.

    Reading the source is the only way to catch a substitution that still *works* — a run row is
    written either way, so a behavioural test would pass against the bug.
    """
    from pathlib import Path

    src = Path("strategy_runtime/manager.py").read_text()
    assert "sid_str = str(uuid.uuid4())" not in src, (
        "strategy_runtime/manager.py substitutes a random uuid for a strategy id that is not a "
        "uuid — which is every Strategy Builder run. The run row is then written against a "
        "strategy that never existed, and nothing can detect it afterwards."
    )
    assert "sid_str = record.spec.strategy_id" in src, "the id must be passed through verbatim"


def test_create_run_sends_the_strategy_id_unchanged():
    """The payload must carry the caller's id, not a normalised variant."""
    captured: dict = {}

    def _capture(payload):
        captured.update(payload)
        return MagicMock(data=[{"id": "run-1"}])

    fake_table = MagicMock()
    fake_table.insert.side_effect = lambda p: _capture(p)
    fake_supabase = MagicMock()
    fake_supabase.table.return_value = fake_table

    service = EngineService()
    with patch("application.services.engine_service.get_supabase", return_value=fake_supabase):
        with patch("application.services.engine_service.async_supabase",
                   side_effect=lambda call, *a, **k: call()):
            asyncio.run(service.create_run("user-1", BUILDER_ID, "paper", "PAPER"))

    assert captured["strategy_id"] == BUILDER_ID


def test_a_legacy_uuid_id_is_also_accepted_unchanged():
    """Both vocabularies must work — that is the point of making the column TEXT."""
    captured: dict = {}

    def _capture(payload):
        captured.update(payload)
        return MagicMock(data=[{"id": "run-2"}])

    fake_table = MagicMock()
    fake_table.insert.side_effect = lambda p: _capture(p)
    fake_supabase = MagicMock()
    fake_supabase.table.return_value = fake_table

    service = EngineService()
    with patch("application.services.engine_service.get_supabase", return_value=fake_supabase):
        with patch("application.services.engine_service.async_supabase",
                   side_effect=lambda call, *a, **k: call()):
            asyncio.run(service.create_run("user-1", LEGACY_ID, "paper", "PAPER"))

    assert captured["strategy_id"] == LEGACY_ID


# ── a missing run must be reported, not indexed into ─────────────────────────────

def _create_run_returning(data):
    service = EngineService()
    with patch("application.services.engine_service.get_supabase", return_value=MagicMock()):
        with patch("application.services.engine_service.async_supabase",
                   return_value=MagicMock(data=data)):
            return asyncio.run(service.create_run("user-1", BUILDER_ID, "paper", "PAPER"))


def test_an_insert_returning_no_row_does_not_raise():
    """The old code did `result.data[0]["id"]` and raised `IndexError`.

    `IndexError` inside a route becomes `INTERNAL_ERROR` with no mention of the run that was never
    recorded, so the caller cannot tell a failed insert from a server fault.
    """
    out = _create_run_returning([])
    assert out["status"] == "error"
    assert out["run_id"] is None


def test_a_missing_data_attribute_is_treated_the_same_way():
    """`data` absent entirely, not just empty — the guard is on the value, not the length."""
    service = EngineService()
    result = MagicMock(spec=[])  # no `.data` attribute at all
    with patch("application.services.engine_service.get_supabase", return_value=MagicMock()):
        with patch("application.services.engine_service.async_supabase", return_value=result):
            out = asyncio.run(service.create_run("user-1", BUILDER_ID, "paper", "PAPER"))
    assert out["status"] == "error"


def test_a_successful_insert_still_reports_running_with_the_run_id():
    """The fix must not turn a good path into an error path."""
    out = _create_run_returning([{"id": "run-abc"}])
    assert out == {"run_id": "run-abc", "status": "running"}


def test_an_error_path_never_reports_running():
    """The specific dishonesty to avoid: claiming a run started when no row exists.

    A phantom "running" strategy is worse than an error — it appears in the runtime dashboard as an
    active strategy with nothing behind it.
    """
    for data in ([], None):
        out = _create_run_returning(data)
        assert out["status"] != "running"
        assert out["run_id"] is None

# ── a run must not be recorded for a strategy that does not exist ────────────────

def _create_run_with_strategies(user_id, strategy_id, existing_legacy=None, existing_built=None):
    """Run `create_run` with the two strategy lookups controlled.

    The patch target is this module's own `async_safe_single` binding. Mocking the query builder
    instead would only test that `async_safe_single` copes with a `MagicMock`, which is not the
    behaviour under test.
    """
    from unittest.mock import AsyncMock

    service = EngineService()

    async def _single(table):
        # `.table(name)` must return something the real query builder can chain `.select().eq()`
        # onto, so the fake is a MagicMock — but it also has to say which table it is, since
        # `str(MagicMock())` is a repr rather than the name.
        name = getattr(table, "_name", "")
        if name == "builder_strategies":
            return {"id": "b"} if existing_built else None
        return {"id": "l"} if existing_legacy else None

    async def _run():
        # `.table(name)` returns the name itself so `_single` can tell the two catalogues apart —
        # `str(MagicMock())` is a repr, not the table name.
        supabase = MagicMock()

        def _table(name):
            m = MagicMock()
            m._name = name
            chain = MagicMock()
            # The name goes on the *chain*, because that is what the query function is handed —
            # `.select().eq()` produces a new object that does not reference the table it came from.
            chain._name = name
            m.select.return_value.eq.return_value = chain
            m.insert.return_value = MagicMock()
            return m

        supabase.table.side_effect = _table
        with patch("application.services.engine_service.get_supabase", return_value=supabase), \
             patch("application.services.engine_service.async_safe_single", AsyncMock(side_effect=_single)):
            with patch("application.services.engine_service.async_supabase",
                       return_value=MagicMock(data=[{"id": "run-x"}])):
                return await service.create_run(user_id, strategy_id, "paper", "PAPER")

    return asyncio.run(_run())


def test_an_unknown_strategy_does_not_get_a_run():
    """The guarantee the dropped foreign key used to provide.

    Making `strategy_id` TEXT required dropping `REFERENCES strategies(id)`, which was the only
    thing rejecting a run for a strategy that does not exist. Without this check,
    `POST /engine/start` answers `{"status": "running"}` for any string, and the runtime dashboard
    shows a live strategy with nothing behind it.
    """
    out = _create_run_with_strategies("u1", "doesnotexist", existing_legacy=None, existing_built=None)
    assert out["status"] == "error"
    assert out["run_id"] is None
    assert "not found" in out["message"].lower()


def test_a_known_legacy_strategy_still_gets_a_run():
    out = _create_run_with_strategies("u1", LEGACY_ID, existing_legacy={"id": LEGACY_ID})
    assert out["status"] == "running"
    assert out["run_id"] == "run-x"


def test_a_builder_strategy_still_gets_a_run():
    """The whole point of the column change: a builder id must be accepted."""
    out = _create_run_with_strategies("u1", BUILDER_ID, existing_built={"id": BUILDER_ID})
    assert out["status"] == "running"
    assert out["run_id"] == "run-x"


def test_an_empty_strategy_id_is_refused():
    out = _create_run_with_strategies("u1", "", existing_legacy={"id": LEGACY_ID})
    assert out["status"] == "error"
    assert out["run_id"] is None


def test_a_failing_lookup_refuses_the_run_rather_than_admitting_it():
    """Unverifiable is not the same as verified.

    A lookup error must not fall through to "assume it exists", or a database blip produces exactly
    the phantom run this check exists to prevent.
    """
    service = EngineService()
    boom = MagicMock()
    boom.table.side_effect = RuntimeError("database unavailable")

    async def _run():
        with patch("application.services.engine_service.get_supabase", return_value=boom):
            return await service.create_run("u1", BUILDER_ID, "paper", "PAPER")

    out = asyncio.run(_run())
    assert out["status"] == "error"
    assert out["run_id"] is None
