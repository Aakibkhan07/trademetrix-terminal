"""`execution_adapter_available` must reflect what is actually registered.

This flag is the single thing the brokers page trusts when it decides whether a broker can be
connected, and it exists because the page used to carry its own hardcoded list of eighteen broker
keys under the heading "not yet available for live trading". All eighteen resolve through
`brokers.get_broker()` — `binance -> BinanceAdapter`, `groww -> GrowwAdapter`, `hdfc ->
HDFCSecuritiesAdapter` — and that list was written in a "design: redesign full frontend" commit on
Sep 22, five days after the adapters and their `register_broker()` calls landed on Sep 17. It was
wrong the day it was written, and it left nine brokers connectable out of twenty-seven.

The flag therefore has to be derived, never declared. These tests assert the derivation agrees with
`get_broker()` for every registered broker, so a future adapter cannot ship without the flag
following it, and a broker that loses its adapter cannot keep advertising one.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brokers import get_broker, list_brokers  # noqa: E402
from brokers.sdk.registry import registry  # noqa: E402


# The eighteen the page used to call "not yet available for live trading". If this set ever grows a
# broker that genuinely has no adapter, it belongs in a test of the *page*, not here — this list is
# the historical claim, and the point is that the backend now contradicts all of it.
PREVIOUSLY_HIDDEN = [
    "hdfc", "iifl", "motilal", "geojit", "reliance", "axis", "binance", "bybit", "okx", "oanda",
    "interactive_brokers", "alpaca", "icici", "aliceblue", "fivepaisa", "finvasia", "flattrade",
    "groww",
]


class TestBrokerAvailabilityFlag:
    def test_every_registered_broker_publishes_the_flag(self):
        """Absent is what let the page's hardcoded list go stale — assert it is never absent."""
        meta = {m["broker"]: m for m in registry.metadata()}
        missing = [name for name in list_brokers() if "execution_adapter_available" not in meta[name]]
        assert missing == [], f"brokers without execution_adapter_available: {missing}"

    def test_flag_matches_the_registered_adapter(self):
        """The flag must be derived from the adapter, not declared alongside it."""
        meta = {m["broker"]: m for m in registry.metadata()}
        mismatched = [
            name for name in list_brokers()
            if meta[name]["execution_adapter_available"] is not (get_broker(name) is not None)
        ]
        assert mismatched == [], f"flag disagrees with get_broker(): {mismatched}"

    def test_all_eighteen_previously_hidden_brokers_are_connectable(self):
        """The regression itself: every broker the page called unavailable resolves to an adapter."""
        assert len(PREVIOUSLY_HIDDEN) == 18
        for name in PREVIOUSLY_HIDDEN:
            adapter = get_broker(name)
            assert adapter is not None, f"{name} has no registered execution adapter"
            meta = {m["broker"]: m for m in registry.metadata()}
            assert meta[name]["execution_adapter_available"] is True, (
                f"{name} has an adapter but metadata says it is unavailable — the page would hide it"
            )

    @pytest.mark.parametrize("name", PREVIOUSLY_HIDDEN)
    def test_each_previously_hidden_broker_has_credential_fields(self, name):
        """The page read one payload and called half of it unusable, while it published fields
        and step-by-step instructions for all of it. Both cannot be true."""
        meta = registry.metadata(name)
        assert meta["fields"], f"{name} publishes no credential fields"
        assert meta["instructions"], f"{name} publishes connect instructions"

    def test_flag_is_not_authored_in_the_registry_file(self):
        """A declared flag would drift again the moment an adapter is added or removed.

        Guards the specific failure this replaced: a hardcoded list, in the frontend, naming brokers
        the backend had already implemented. If someone adds a second source of truth here, this
        fails rather than letting the page and the backend disagree quietly.
        """
        source = (Path(__file__).resolve().parents[1] / "brokers" / "sdk" / "registry.py").read_text()
        assert "self.adapter_class is not None" in source, (
            "the flag must be derived from the adapter class it is describing"
        )

    def test_no_hardcoded_broker_list_remains_in_the_brokers_page(self):
        """The other half of the fix. The page must not carry its own opinion about which brokers
        exist — that is exactly what made the claim false."""
        page = Path(__file__).resolve().parents[2] / "web" / "app" / "brokers" / "page.tsx"
        if not page.exists():  # the API suite runs without the web app present
            pytest.skip("web app not present")
        text = page.read_text()
        assert "PLACEHOLDER_BROKERS" not in text, (
            "the hardcoded placeholder list is back; the page must read execution_adapter_available"
        )

        # Comments are stripped first. The first version of this test grepped the whole file and
        # passed with a hardcoded list back in place, because the field name it looked for also
        # appears in the explanatory comment above the function — the mutation reintroduced a
        # seventeen-entry `includes()` and the test stayed green. A guard that a comment can satisfy
        # is not a guard.
        import re as _re

        code = _re.sub(r"/\*.*?\*/", "", text, flags=_re.S)
        code = _re.sub(r"^\s*//.*$", "", code, flags=_re.M)
        code = _re.sub(r"//[^\n]*$", "", code, flags=_re.M)

        assert "execution_adapter_available" in code, (
            "the page must decide availability from the metadata the registry publishes"
        )
        # and it must not be reading a broker list of its own to do it
        assert not _re.search(r"new Set\(\s*\[", code), (
            "the page is building a broker list locally; availability must come from the server"
        )
