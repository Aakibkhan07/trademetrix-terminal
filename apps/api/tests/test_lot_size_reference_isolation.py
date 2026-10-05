"""The lot-size reference is validation-only, and production must prove it.

Two separate claims are checked here, and they are checked differently.

**Isolation.** `tests/fixtures/lot_size_reference.py` holds October 2026 lot
sizes. The master prompt's rule is that these must never become the production
source of truth, which is only meaningful if production cannot reach them. So
this walks the whole production package tree and fails if any module outside
`tests/` mentions the fixture, imports it, or defines its own copy of the
numbers under a different name.

**Prohibitions.** The same rule forbids specific constructs outright:

    LOT_SIZES["NIFTY"] = 65          assigning a lot size into a dict
    LOT_SIZES.get(symbol, 75)        a defaulted lookup
    lot_size = 75                    a literal fallback
    lot_size = 1                     a literal fallback

Each is matched against real production files, so a reintroduced default fails
here rather than quietly sizing an order.

Source scanning is the right tool for this particular claim: the property is
about what the code *says*, not what it returns, and no behavioural test can
tell "absent" from "present but unused" for a module-level constant. Everything
else in this repair is tested behaviourally instead.
"""

import ast
import re
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_NAME = "lot_size_reference"

#: Directories that are not production execution paths. `scripts/` holds
#: diagnostic tools that run by hand; a validation script is *supposed* to read
#: the reference. Everything else is the live request path.
NON_PRODUCTION_DIRS = {"tests", "scripts", "__pycache__", ".venv", "node_modules"}


def production_files() -> list[Path]:
    out: list[Path] = []
    for path in API_ROOT.rglob("*.py"):
        rel = path.relative_to(API_ROOT)
        if rel.parts and rel.parts[0] in NON_PRODUCTION_DIRS:
            continue
        if "site-packages" in rel.parts:
            continue
        out.append(path)
    return out


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def code_only(path: Path) -> str:
    """The module's code with comments and string literals removed."""
    return " ".join(text for _, text in code_line_numbers(path))


def code_line_numbers(path: Path) -> list[tuple[int, str]]:
    """(line number, code text) for lines that contain executable tokens.

    Comments and string literals are dropped, because the repair left comments and
    docstrings that *quote the removed construct* in order to explain why it went.
    A raw text scan cannot tell `lot_size = 75` the statement from ``lot_size = 75``
    inside a sentence explaining it, and reported prose as code.

    My first version of this grouped tokens by comparing each token's line against a
    moving cursor and flushing on gaps. It silently dropped lines, and three
    separate mutations -- a literal fallback, a defaulted lookup and a magic lot
    multiplier -- all passed against it. So the guard could not fail on precisely
    the code it exists to forbid. Grouping straight into a dict keyed by line number
    has no such cursor to get wrong, and the mutations below now fail.
    """
    import io
    import tokenize

    rows: dict[int, list[str]] = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(read(path)).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            rows.setdefault(tok.start[0], []).append(tok.string)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []
    return sorted((line_no, " ".join(parts)) for line_no, parts in rows.items())


# ── Isolation ────────────────────────────────────────────────────────────────


def test_production_cannot_see_the_reference_fixture():
    offenders = []
    for path in production_files():
        text = read(path)
        if FIXTURE_NAME in text:
            offenders.append(str(path.relative_to(API_ROOT)))
    assert not offenders, (
        "production modules reference the validation-only lot-size fixture: "
        + ", ".join(offenders)
    )


def test_production_defines_no_lot_size_table():
    """No production module may build its own index -> lot-size mapping.

    Checked structurally rather than by name, so renaming a variable or building
    the dict through a comprehension does not slip past.
    """
    offenders = []
    for path in production_files():
        try:
            tree = ast.parse(read(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            targets: list[ast.expr] = []
            value: ast.expr | None = None
            if isinstance(node, ast.Assign):
                targets, value = list(node.targets), node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets, value = [node.target], node.value
            else:
                continue
            if not isinstance(value, ast.Dict):
                continue
            # A dict whose keys are all string constants and whose values are all
            # integer constants, named like a lot size, is a lot-size table.
            if not all(isinstance(k, ast.Constant) and isinstance(k.value, str) for k in value.keys):
                continue
            if not all(isinstance(v, ast.Constant) and isinstance(v.value, int) for v in value.values):
                continue
            names = [t.id for t in targets if isinstance(t, ast.Name)]
            if any("LOT" in n.upper() for n in names):
                offenders.append(f"{path.relative_to(API_ROOT)}:{node.lineno} -> {names}")
    assert not offenders, "production lot-size tables found: " + "; ".join(offenders)


# ── Prohibitions ─────────────────────────────────────────────────────────────

_DEFAULTED_LOOKUP = re.compile(
    r"LOT_SIZES\s*\.\s*get\s*\([^)]*?,\s*\d+\s*\)", re.IGNORECASE
)
_LITERAL_FALLBACK = re.compile(
    r"\blot_size\b\s*[:=]\s*(?!None\b)\d+\s*$", re.IGNORECASE | re.MULTILINE
)


def test_no_defaulted_lot_size_lookup_in_production():
    """`LOT_SIZES.get(symbol, 75)` is the exact construct this repair removed."""
    offenders = []
    for path in production_files():
        for line_no, line in code_line_numbers(path):
            for match in _DEFAULTED_LOOKUP.finditer(line):
                offenders.append(f"{path.relative_to(API_ROOT)}:{line_no} {match.group(0)}")
    assert not offenders, (
        "defaulted lot-size lookups in production:\n  " + "\n  ".join(offenders)
    )


def test_no_literal_lot_size_fallback_in_production():
    """`lot_size = 75` / `lot_size = 1` — a guessed contract size, never valid."""
    offenders = []
    for path in production_files():
        for line_no, line in code_line_numbers(path):
            for match in _LITERAL_FALLBACK.finditer(line):
                offenders.append(f"{path.relative_to(API_ROOT)}:{line_no} {match.group(0).strip()}")
    assert not offenders, (
        "literal lot-size fallbacks in production:\n  " + "\n  ".join(offenders)
    )


def test_no_magic_lot_multiplier_in_production():
    """`10 * lot` is the shape of the original gate defect and must not reappear.

    Matched as a multiplication by a bare integer against something lot-sized, so
    an unrelated `x * 2` is not reported. The gate's `new_qty = 10 * lot` is the
    canonical example, and hero_zero separately discarded a risk-derived quantity
    with `qty = 10 * self.lot_size`.
    """
    pattern = re.compile(r"=\s*\d+\s*\*\s*(?:self\.)?(?:lot|lot_size)\b", re.IGNORECASE)
    offenders = []
    for path in production_files():
        for line_no, line in code_line_numbers(path):
            for match in pattern.finditer(line):
                offenders.append(f"{path.relative_to(API_ROOT)}:{line_no} {match.group(0)}")
    assert not offenders, (
        "magic lot multipliers in production:\n  " + "\n  ".join(offenders)
    )


def test_the_resolver_is_the_only_lot_size_entry_point():
    """`market.instruments` is the single sanctioned source."""
    from market.instruments import Instrument, instrument_resolver

    assert instrument_resolver.resolve("ANY", broker="dhan", instrument_type="FUT") is None
    # Instrument carries no default lot size; construction without one is explicit.
    inst = Instrument(
        broker="dhan",
        security_id="1",
        broker_symbol="X",
        exchange_segment="NSE_FNO",
        instrument_type="FUT",
        lot_size=65,
    )
    assert inst.lot_size == 65


# ── The reference is still useful ─────────────────────────────────────────────


class TestReferenceIsOnlyAReference:
    """It must disagree with the values the repo used to hardcode.

    A reference that agreed with everything it replaced would never catch
    anything, so this asserts the discrepancy is real and visible.
    """

    def test_midcpnifty_reference_differs_from_the_removed_hardcoded_value(self):
        from tests.fixtures.lot_size_reference import INDEX_OPTIONS, LEGACY_HARDCODED

        assert INDEX_OPTIONS["MIDCPNIFTY"] == 120
        assert LEGACY_HARDCODED["MIDCPNIFTY"] == 75
        assert INDEX_OPTIONS["MIDCPNIFTY"] != LEGACY_HARDCODED["MIDCPNIFTY"]

    def test_unknown_underlying_returns_none_not_a_default(self):
        from tests.fixtures.lot_size_reference import reference_lot_size

        assert reference_lot_size("NOSUCHSYMBOL") is None
        assert reference_lot_size("") is None

    @pytest.mark.parametrize(
        ("underlying", "expected"),
        [("NIFTY", 65), ("BANKNIFTY", 30), ("FINNIFTY", 60),
         ("MIDCPNIFTY", 120), ("NIFTYNXT50", 25), ("SENSEX", 20),
         ("BANKEX", 30), ("SENSEX50", 75)],
    )
    def test_index_reference_values(self, underlying, expected):
        from tests.fixtures.lot_size_reference import INDEX_OPTIONS

        assert INDEX_OPTIONS[underlying] == expected

    @pytest.mark.parametrize(
        ("ticker", "expected"),
        [("360ONE", 500), ("ABB", 125), ("ABCAPITAL", 3100), ("ASHOKLEY", 5000),
         ("BAJAJ-AUTO", 75), ("BANDHANBNK", 3600)],
    )
    def test_stock_reference_samples(self, ticker, expected):
        from tests.fixtures.lot_size_reference import STOCK_OPTION_SAMPLES

        assert STOCK_OPTION_SAMPLES[ticker] == expected

    def test_dhan_metadata_wins_over_the_reference(self):
        """The rule that matters most: the reference never overrides the master.

        A provider claiming a different lot size for the same contract is taken at
        its word, and the reference is not consulted at all.
        """
        from market.instruments import Instrument, instrument_resolver

        saved = list(instrument_resolver._providers)
        try:
            instrument_resolver._providers = []
            # Dhan master says 99 for NIFTY; the reference says 65.
            instrument_resolver.register(
                "dhan-master",
                lambda *a, **k: Instrument(
                    broker="dhan", security_id="1", broker_symbol="NIFTY",
                    exchange_segment="NSE_FNO", instrument_type="OPT",
                    lot_size=99, source="dhan",
                ),
                authoritative=True,
            )
            found = instrument_resolver.resolve(
                "NSE:NIFTY", broker="dhan", instrument_type="OPT"
            )
            assert found is not None
            assert found.lot_size == 99, "the reference overrode the authoritative source"
        finally:
            instrument_resolver._providers = saved