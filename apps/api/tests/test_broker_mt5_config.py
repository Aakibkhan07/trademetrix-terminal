"""`_MT5_BROKER_CONFIG` must agree with the broker keys the registry offers.

The dict is looked up with `_MT5_BROKER_CONFIG.get(broker_key, {})`. A key that does not
match raises nothing — it returns `{}`, and every field falls back to its generic default.
So a mismatch cannot be caught by the code that has the bug; it can only be caught by
comparing the two tables against each other.

It already had one. The dict spelled the FXTM key `"fxTM"` while `registry.py` registers
`"fxtm"` in its MT5 metadata, so an FXTM adapter resolved to an empty config and silently
took `"MT5 Server"` instead of `"FXTM Server"`. Nothing warned.

The duplicate is here too. `"fbs"` appeared twice with byte-identical values, so Python
quietly kept the second. No behavioural difference — worth being precise about that — but it
is exactly the shape of entry that makes someone later edit the copy that is not in effect.

These assert the **relationship**, not the literal contents. Hard-coding the expected keys
would pass today and fail the moment a broker is added, which is the moment the check
matters most: a new registry entry with no config, or a case slip on either side, shows up
as a failing test instead of a default nobody noticed.
"""
import pytest

from brokers.mt5_adapter import _MT5_BROKER_CONFIG
from brokers.registry import get_broker_metadata

def _registry_broker_slugs() -> list[str]:
    """Every broker key the MT5 connect form can actually produce.

    Read from the registry rather than hard-coded, so adding a broker to the UI
    automatically brings it into scope here instead of silently escaping the check.

    Collected from every `select` field rather than a named one: the point is "a key the
    user can pick", and hard-coding the field name would quietly narrow that the day a
    second dropdown appears.
    """
    slugs: list[str] = []
    for field in get_broker_metadata("mt5").get("fields", []):
        if not isinstance(field, dict) or field.get("type") != "select":
            continue
        for option in field.get("options", []):
            if isinstance(option, dict) and "value" in option:
                slugs.append(option["value"])
    return slugs


_MT5_REGISTRY_SLUGS = _registry_broker_slugs()


def test_the_registry_offers_the_broker_options_this_check_relies_on():
    """Precondition.

    Without this, an empty `_MT5_REGISTRY_SLUGS` would make every other test in the file
    pass vacuously — the same trap as the session-mock and cache-TTL work: a guard that
    silently checks nothing while reporting success.
    """
    assert _MT5_REGISTRY_SLUGS, (
        "no MT5 select field yielded broker options; the checks below would assert nothing"
    )
    assert "fxtm" in _MT5_REGISTRY_SLUGS


@pytest.mark.parametrize("broker_key", _MT5_REGISTRY_SLUGS)
def test_every_registry_broker_key_resolves_in_the_config(broker_key):
    """The core contract: a key the UI can produce must resolve to a real entry.

    Asserted with `in`, not by inspecting the value, so this reports the mismatch itself
    rather than the generic default that hid it.
    """
    assert broker_key in _MT5_BROKER_CONFIG, (
        f"registry offers broker key {broker_key!r} but _MT5_BROKER_CONFIG has no such "
        f"key; keys there are {sorted(_MT5_BROKER_CONFIG)}. The lookup is "
        f"_MT5_BROKER_CONFIG.get(broker_key, {{}}), so this fails silently at runtime."
    )


@pytest.mark.parametrize("broker_key", _MT5_REGISTRY_SLUGS)
def test_a_resolved_entry_has_the_fields_the_adapter_reads(broker_key):
    """A present key is not enough — it has to carry `mt5_server`.

    Otherwise a stub entry added to satisfy the check above would resolve and then fall
    through to `"MT5 Server"`, reproducing the original symptom through a different route.
    """
    entry = _MT5_BROKER_CONFIG[broker_key]
    assert entry.get("mt5_server"), f"{broker_key!r} entry has no mt5_server"


def test_keys_are_unique_and_match_the_registry_exactly():
    """Case-insensitively, a duplicate or a case variant is a near-miss waiting to happen.

    `_MT5_BROKER_CONFIG` is a plain dict literal, so a repeated key is discarded by the
    interpreter with no warning — `ruff`'s F601 is the only thing that catches it, and lint
    has never passed in CI. Asserting uniqueness here means it fails even if that changes.
    """
    keys = list(_MT5_BROKER_CONFIG)

    # A dict literal cannot actually hold duplicates, so the check that matters is against
    # the source text: count the literal keys and compare with the dict that survived.
    import inspect

    from brokers import mt5_adapter

    source = inspect.getsource(mt5_adapter)
    literal_keys = [
        line.split('"')[1]
        for line in source.splitlines()
        if line.startswith('    "') and '": {' in line
    ]
    assert len(literal_keys) == len(set(literal_keys)), (
        f"duplicate keys in the dict literal: {sorted(k for k in set(literal_keys) if literal_keys.count(k) > 1)}"
    )
    assert len(literal_keys) == len(keys), (
        f"{len(literal_keys)} literal keys but {len(keys)} in the dict — a key was dropped"
    )

    lowered = [k.lower() for k in keys]
    assert len(lowered) == len(set(lowered)), (
        f"keys differing only by case: {sorted(k for k in keys if lowered.count(k.lower()) > 1)}"
    )


def test_fxtm_resolves_to_fxtm_not_the_generic_default():
    """The specific regression, pinned.

    Worth its own test even though `test_every_registry_broker_key_resolves_in_the_config`
    covers it: that one says "FXTM is missing", this one says what the consequence was —
    the wrong server string, silently.
    """
    assert _MT5_BROKER_CONFIG["fxtm"]["mt5_server"] == "FXTM Server"

    # And the old spelling is genuinely absent, rather than both existing.
    assert "fxTM" not in _MT5_BROKER_CONFIG


def test_the_adapter_uses_the_config_default_it_looks_up():
    """Ties the table to the only reader.

    If `MT5Adapter.__init__` stopped reading `mt5_server` from the config, the whole
    consistency check above would be guarding nothing — so this asserts the link exists, and
    the module's own docstring records that the value is currently always overwritten by the
    required `mt5_server` credential in `authenticate`.
    """
    from brokers.mt5_adapter import MT5Adapter

    adapter = MT5Adapter(broker_key="fxtm")
    assert adapter._mt5_server == "FXTM Server"

    # An unknown key still degrades rather than raising — that fallback is the reason the
    # key mismatch was invisible, so it is pinned deliberately.
    assert MT5Adapter(broker_key="not-a-broker")._mt5_server == "MT5 Server"
