"""`auth_verified` must reach the UI and must default to visible.

Two defects this pins:

1. If the flag is absent from metadata, the page must NOT hide the broker. An older API
   or a newly-registered broker omits the field, and hiding a working broker because the
   server did not mention it is worse than showing an unverified one. Only an explicit
   `false` withholds the Connect button.

2. The flag must be derived from the spec, never hardcoded in the frontend. The previous
   hardcoded broker list was already wrong once (18 working brokers hidden); a second
   hardcoded list would repeat that class of defect.
"""

from __future__ import annotations

from pathlib import Path

from brokers.sdk.registry import BrokerRegistry, BrokerSpec

PAGE = Path(__file__).resolve().parents[2] / "web" / "app" / "brokers" / "page.tsx"


class TestMetadataCarriesTheFlag:
    def test_to_metadata_includes_auth_verified(self) -> None:
        meta = BrokerSpec(name="x", display_name="X", auth_verified=False).to_metadata()
        assert "auth_verified" in meta, "the UI cannot gate on a field it never receives"
        assert meta["auth_verified"] is False

    def test_unset_is_none_not_false(self) -> None:
        """None means 'not measured' and must not read as 'broken'."""
        assert BrokerSpec(name="x", display_name="X").to_metadata()["auth_verified"] is None

    def test_registry_register_accepts_the_flag(self) -> None:
        reg = BrokerRegistry()
        spec = reg.register(name="probe", display_name="Probe", auth_verified=False)
        assert spec.auth_verified is False

    def test_registry_register_defaults_to_none(self) -> None:
        reg = BrokerRegistry()
        assert reg.register(name="probe2", display_name="Probe2").auth_verified is None


class TestUiGating:
    def _page(self) -> str:
        return PAGE.read_text(encoding="utf-8")

    def test_page_reads_the_backend_flag(self) -> None:
        code = self._page()
        assert "auth_verified" in code, (
            "the page must gate on the backend flag, not a local list"
        )

    def test_absent_flag_does_not_hide_the_broker(self) -> None:
        """`undefined` must mean available — omission is not a failure signal."""
        code = self._page()
        assert "!== false" in code, (
            "gating on truthiness would hide every broker from an older API that "
            "omits the field"
        )

    def test_no_hardcoded_broker_allowlist(self) -> None:
        """A hardcoded list is a snapshot of the backend at some past moment."""
        code = self._page()
        for banned in ("'dhan'", '"dhan"', "'zerodha'", '"zerodha"'):
            # a mention inside the gating logic itself would also be wrong, so check
            # the filter expressions specifically
            for line in code.splitlines():
                if banned in line and ("filter(" in line or "some(" in line):
                    raise AssertionError(
                        f"hardcoded broker key in filtering logic: {line.strip()!r}"
                    )

    def test_gating_uses_the_verified_predicate(self) -> None:
        code = self._page()
        assert "isAuthVerified(metadataMap[b])" in code, (
            "availableBrokers must be filtered by auth verification"
        )


class TestProductionRegistrations:
    def test_dhan_and_upstox_recorded_unverified(self) -> None:
        """Both were measured broken against their live APIs; the flag must say so."""
        from brokers.registry import get_broker_metadata

        meta = {m["broker"]: m for m in get_broker_metadata()}
        assert meta["dhan"].get("auth_verified") is False
        assert meta["upstox"].get("auth_verified") is False

    def test_zerodha_not_marked_broken(self) -> None:
        """A guard against a flag flipped too broadly and hiding working brokers."""
        from brokers.registry import get_broker_metadata

        meta = {m["broker"]: m for m in get_broker_metadata()}
        assert meta["zerodha"].get("auth_verified") is not False