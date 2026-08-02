"""BrokerRegistry — single source of truth for broker adapters.

A registered BrokerSpec carries:
- the adapter class (must subclass brokers.base.BaseBroker),
- UI metadata (auth type, fields, instructions) — formerly brokers/registry.py,
- the capability set — formerly the static dict in execution/broker_adapter.py,
- whether the broker has OAuth etc.

`create(name)` keeps the existing factory contract: returns a
CircuitBreakerBroker-wrapped adapter (breaker name `broker_{name}`), so all current
callers (BrokerExecutionAdapter, TokenManager) behave identically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from brokers.sdk.capabilities import BrokerCapabilities, CapabilityFlag, get_capabilities
from brokers.sdk.errors import UnsupportedFeatureError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BrokerSpec:
    name: str
    display_name: str
    auth_type: str = "oauth"
    description: str = ""
    fields: list[dict] = field(default_factory=list)
    additional_params_fields: list[dict] = field(default_factory=list)
    has_additional_params: bool = False
    instructions: str = ""
    oauth_available: bool = False
    adapter_class: type | None = None
    capabilities: BrokerCapabilities | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_metadata(self) -> dict[str, Any]:
        """Legacy UI metadata payload (shape of brokers/registry.py get_broker_metadata)."""

        return {
            "broker": self.name,
            "display_name": self.display_name,
            "auth_type": self.auth_type,
            "description": self.description,
            "fields": self.fields,
            "has_additional_params": self.has_additional_params,
            "instructions": self.instructions,
            "oauth_available": self.oauth_available,
            **({"additional_params_fields": self.additional_params_fields} if self.has_additional_params else {}),
        }

    def capability_flags(self) -> set[CapabilityFlag]:
        return set((self.capabilities or get_capabilities(self.name))._caps)  # noqa: SLF001 - internal access


class BrokerRegistry:
    """Thread-safe registry of broker specs.

    Lookup is by broker name. Registration requires a unique name; re-registration
    overwrites (idempotent for tests) but logs a warning.
    """

    def __init__(self) -> None:
        self._specs: dict[str, BrokerSpec] = {}

    # ── registration ────────────────────────────────────────────────

    def register(
        self,
        spec: BrokerSpec | None = None,
        *,
        name: str = "",
        display_name: str = "",
        adapter_class: type | None = None,
        capabilities: BrokerCapabilities | None = None,
        meta: dict[str, Any] | None = None,
    ) -> BrokerSpec:
        if spec is None:
            if not name:
                raise ValueError("Broker name is required")
            spec = BrokerSpec(name=name, display_name=display_name or name, adapter_class=adapter_class)
            if meta:
                for key, value in meta.items():
                    if hasattr(spec, key) and key not in ("name",):
                        setattr(spec, key, value)
                    else:
                        spec.meta[key] = value
        if spec.name in self._specs:
            logger.warning("Broker %s re-registered — overwriting spec", spec.name)
        if spec.capabilities is None:
            # Inherit the adapter's own broker identity when available (e.g. tests
            # registering FyersAdapter under a different name), else the spec name.
            adapter_broker = getattr(getattr(spec, "adapter_class", None), "broker_name", "") or spec.name
            spec.capabilities = get_capabilities(adapter_broker)
        self._specs[spec.name] = spec
        return spec

    def unregister(self, name: str) -> None:
        self._specs.pop(name, None)

    # ── lookups ─────────────────────────────────────────────────────

    def spec(self, name: str) -> BrokerSpec:
        if name not in self._specs:
            raise ValueError(f"Unknown broker: {name}. Available: {sorted(self._specs)}")
        return self._specs[name]

    def __contains__(self, name: str) -> bool:
        return name in self._specs

    def names(self) -> list[str]:
        return sorted(self._specs)

    def list(self) -> list[BrokerSpec]:
        return [self._specs[n] for n in self.names()]

    # ── capabilities ────────────────────────────────────────────────

    def capabilities(self, name: str) -> BrokerCapabilities:
        return self.spec(name).capabilities or get_capabilities(name)

    def capability_matrix(self) -> dict[str, dict[str, Any]]:
        return {n: s.capabilities.to_dict() if s.capabilities else get_capabilities(n).to_dict() for n, s in self._specs.items()}

    def supports(self, name: str, capability: CapabilityFlag | str) -> bool:
        return self.capabilities(name).supports(capability)

    def require(self, name: str, capability: CapabilityFlag | str) -> None:
        if name not in self._specs:
            raise ValueError(f"Unknown broker: {name}")
        self.capabilities(name).require(capability)

    # ── factory ─────────────────────────────────────────────────────

    def create(self, name: str, *, wrap_circuit_breaker: bool = True) -> Any:
        """Instantiate the adapter for `name`.

        Returns a CircuitBreakerBroker-wrapped adapter by default — identical to the
        legacy brokers.create_broker() contract. `wrap_circuit_breaker=False` returns
        the raw adapter (used by transports / tests).
        """

        spec = self.spec(name)
        if spec.adapter_class is None:
            raise ValueError(f"Broker {name} has no adapter_class registered")
        adapter = spec.adapter_class()
        if not wrap_circuit_breaker:
            return adapter
        from brokers.circuit_breaker_broker import CircuitBreakerBroker

        return CircuitBreakerBroker(adapter, breaker_name=f"broker_{name}")

    # ── metadata (legacy UI contract) ───────────────────────────────

    def metadata(self, broker: str | None = None) -> list[dict] | dict:
        if broker:
            return self.spec(broker).to_metadata()
        return [self._specs[n].to_metadata() for n in self.names()]

    # ── discovery helper ────────────────────────────────────────────

    def missing_capability(self, name: str, capability: CapabilityFlag | str) -> UnsupportedFeatureError:
        caps = self.capabilities(name)
        return UnsupportedFeatureError(
            CapabilityFlag(capability).value if not isinstance(capability, CapabilityFlag) else capability.value,
            broker=name,
            detail=f"Capability not declared for broker {name} (declared: {sorted(caps.capabilities)})",
        )


registry: BrokerRegistry = BrokerRegistry()


def get_registry() -> BrokerRegistry:
    return registry
