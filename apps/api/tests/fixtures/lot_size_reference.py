"""October 2026 lot-size reference — VALIDATION ONLY. NEVER A PRODUCTION SOURCE.

Read this before using anything in this file.

The values here are a *sanity check* for the instrument resolver. The single
source of truth for a contract's lot size is the authoritative Dhan
instrument/contract master, reached through
:class:`market.instruments.InstrumentResolver`. Production execution never
imports this module, and `tests/test_lot_size_reference_isolation.py` asserts
that: it walks the production package tree and fails if any module outside
`tests/` references this file or its constants.

Why it exists at all: when the Dhan master is wired up, it is worth knowing
whether it agrees with the sizes brokers were publishing in October 2026. A
mismatch is a signal to investigate, not a value to enforce. When Dhan says
something different, **Dhan wins** and the difference is logged by
`scripts/validate_dhan_lot_sizes.py`. This file must never be the tie-breaker,
and no code path may fall back to it.

What it must never become:

    LOT_SIZES["NIFTY"] = 65          # forbidden
    LOT_SIZES.get(symbol, 75)        # forbidden
    lot_size = 75                    # forbidden
    lot_size = 1                     # forbidden
    infer lot size from the symbol name  # forbidden

There are 200+ F&O underlyings and their lot sizes vary by underlying and
change on expiry-cycle revisions. A hardcoded dictionary goes stale silently
and then sizes a real order wrongly, which is the failure this whole repair
exists to remove. Per-underlying stock sizes belong in the Dhan master, not here.

Scope of the samples below:

* `INDEX_OPTIONS` is the complete October 2026 index set.
* `STOCK_OPTION_SAMPLES` is 30 illustrative values supplied for test variety.
  It is explicitly NOT exhaustive and NOT a source. Stock lot sizes must be
  read from contract metadata at resolution time.
"""

from __future__ import annotations

# ── Index option lot sizes, October 2026 ──────────────────────────────────────
INDEX_OPTIONS: dict[str, int] = {
    "NIFTY": 65,
    "BANKNIFTY": 30,
    "FINNIFTY": 60,
    "MIDCPNIFTY": 120,
    "NIFTYNXT50": 25,
    "SENSEX": 20,
    "BANKEX": 30,
    "SENSEX50": 75,
}

# ── Illustrative stock-option samples. NOT exhaustive, NOT a source. ─────────
STOCK_OPTION_SAMPLES: dict[str, int] = {
    "360ONE": 500,
    "ABB": 125,
    "ABCAPITAL": 3100,
    "ADANIENSOL": 675,
    "ADANIENT": 309,
    "ADANIGREEN": 600,
    "ADANIPORTS": 475,
    "ADANIPOWER": 3550,
    "ALKEM": 125,
    "AMBER": 100,
    "AMBUJACEM": 1200,
    "ANGELONE": 2500,
    "APLAPOLLO": 350,
    "APOLLOHOSP": 125,
    "ASHOKLEY": 5000,
    "ASIANPAINT": 250,
    "ASTRAL": 425,
    "ATHERENERG": 375,
    "AUBANK": 1000,
    "AUROPHARMA": 550,
    "AXISBANK": 625,
    "BAJAJ-AUTO": 75,
    "BAJAJFINSV": 300,
    "BAJAJHLDNG": 75,
    "BAJFINANCE": 750,
    "BANDHANBNK": 3600,
}

#: Symbols this project has historically hardcoded, mapped to their October 2026
#: reference lot size. Used by tests to prove the hardcoded dicts were wrong.
#:
#: MIDCPNIFTY is the interesting one: the repository carried 75 while the
#: October 2026 reference is 120. Any strategy or gate still holding the old
#: value is sizing a position 37% away from the contract.
LEGACY_HARDCODED: dict[str, int] = {
    "NIFTY": 65,
    "BANKNIFTY": 30,
    "FINNIFTY": 60,
    "MIDCPNIFTY": 75,   # repo value; reference is 120
    "SENSEX": 20,
}


def reference_lot_size(underlying: str) -> int | None:
    """October 2026 reference lot size, or None when we hold no opinion.

    Returns None rather than a default for an unknown symbol. A test that reads
    None is told "no reference available"; a test that reads 75 is told
    something false.
    """
    key = (underlying or "").upper()
    return INDEX_OPTIONS.get(key) or STOCK_OPTION_SAMPLES.get(key)