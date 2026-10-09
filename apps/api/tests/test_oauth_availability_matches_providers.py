"""`oauth_available` must mean "the generic OAuth endpoint serves this broker".

Production defect: Zerodha was registered with `oauth_available: True`, but Kite
Connect is not OAuth. It is a two-legged request_token flow served by its own
endpoints:

    GET  /brokers/zerodha/login-url
    POST /brokers/zerodha/exchange-request-token
    GET  /brokers/zerodha/callback

The UI calls `GET /{broker}/auth-url` whenever `oauth_available` is true, and there
is no `BrokerOAuthProvider` for Zerodha, so that raised
`ValueError: No OAuth provider for broker: zerodha`. Measured on production: 6 of 6
Zerodha credentials could not obtain an auth URL — every one of those users got a
button that failed when pressed.

The invariant is a set equality, not a spot check: a broker may not claim OAuth
without a provider, and a provider may not exist without its broker claiming it.
Either drift means a button that cannot work.
"""

from __future__ import annotations

import pytest

from brokers.registry import get_broker_metadata
from infrastructure.oauth_providers import get_oauth_provider


def _meta() -> dict[str, dict]:
    return {m["broker"]: m for m in get_broker_metadata()}


def _brokers_with_providers() -> set[str]:
    """Every key of the provider registry, discovered rather than hardcoded."""
    from infrastructure import oauth_providers

    return set(oauth_providers._oauth_providers)  # noqa: SLF001 - the registry is the source


class TestOAuthAvailabilityMatchesProviders:
    def test_claiming_oauth_requires_a_provider(self) -> None:
        claimed = {b for b, m in _meta().items() if m.get("oauth_available")}
        with_provider = _brokers_with_providers()
        orphans = claimed - with_provider
        assert orphans == set(), (
            "these brokers advertise OAuth, so the UI shows an Authorize button that "
            f"calls GET /{{broker}}/auth-url, but no provider exists: {sorted(orphans)}"
        )

    def test_every_provider_is_claimed_by_its_broker(self) -> None:
        claimed = {b for b, m in _meta().items() if m.get("oauth_available")}
        unclaimed = _brokers_with_providers() - claimed
        assert unclaimed == set(), (
            "these brokers have a working OAuth provider but the UI does not offer it, "
            f"so a working connect flow stays hidden: {sorted(unclaimed)}"
        )

    def test_zerodha_does_not_claim_oauth(self) -> None:
        """The specific regression. Kite Connect is a request_token flow, not OAuth."""
        assert _meta()["zerodha"].get("oauth_available") is False

    def test_zerodha_declares_its_own_flow(self) -> None:
        """The UI needs to know to render the Kite button, not the generic Authorize."""
        assert _meta()["zerodha"].get("connect_flow") == "kite_request_token"

    @pytest.mark.parametrize("broker", ["fyers", "dhan", "upstox"])
    def test_the_three_real_oauth_brokers_still_work(self, broker: str) -> None:
        """A guard against 'fixing' this by switching OAuth off everywhere."""
        assert _meta()[broker].get("oauth_available") is True
        assert get_oauth_provider(broker) is not None

    def test_provider_builds_a_usable_url(self) -> None:
        """Claiming OAuth means the URL endpoint must actually answer."""
        from application.interfaces.broker_oauth import BrokerOAuthConfig

        for broker in sorted(_brokers_with_providers()):
            url = get_oauth_provider(broker).build_auth_url(
                BrokerOAuthConfig(
                    client_id="TESTCLIENT",
                    redirect_uri=f"https://api.example.com/brokers/{broker}/callback",
                ),
                "state123",
            )
            assert url.startswith("https://"), f"{broker} produced {url!r}"
            assert "client_id=TESTCLIENT" in url, f"{broker} dropped the client id"
            assert "state=state123" in url, f"{broker} dropped the CSRF state"


class TestGenericAuthUrlEndpoint:
    def test_generic_endpoint_serves_every_claiming_broker(self) -> None:
        """The exact call the UI makes must not raise for any advertised broker."""
        for broker in sorted(_brokers_with_providers()):
            get_oauth_provider(broker)  # must not raise