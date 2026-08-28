"""
Ports (interfaces) for the execution engine.

These are the seams where YOUR existing platform plugs in. The engine depends
only on these Protocols, so you can swap in your real RiskGuard / OrderManager /
subscription store without touching engine.py. Reference implementations live in
sizing.py, subscribers.py, adapters.py and default to safe behaviour.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import (
    Signal,
    Subscriber,
    UserTradingProfile,
    OrderIntent,
    ExecutionResult,
)


@runtime_checkable
class SubscriberStore(Protocol):
    async def live_subscribers(self, strategy_id: str) -> list[Subscriber]:
        """Users subscribed to this strategy who also have a LIVE broker link."""
        ...


@runtime_checkable
class ProfileStore(Protocol):
    async def profile(self, user_id: str) -> UserTradingProfile:
        """Per-user capital / mode / risk settings (tier-gated)."""
        ...


@runtime_checkable
class PositionSizer(Protocol):
    def size(self, profile: UserTradingProfile, signal: Signal) -> int:
        """Return quantity (multiple of lot_size). 0 = do not trade."""
        ...


@runtime_checkable
class RiskGuard(Protocol):
    async def check(self, profile: UserTradingProfile, intent: OrderIntent) -> tuple[bool, str | None]:
        """
        (allowed, reason). Wrap YOUR existing RiskGuard here — daily loss cap,
        exposure limits, tier rules. Return (False, reason) to block.
        """
        ...


@runtime_checkable
class TradingAdapter(Protocol):
    broker: str

    async def place_order(self, intent: OrderIntent, access_token: str) -> ExecutionResult:
        """
        Place a real order at the broker using the vault access token.
        PaperTradingAdapter simulates; live adapters call the broker API.
        Must NOT raise — return an ExecutionResult with status.
        """
        ...


@runtime_checkable
class Notifier(Protocol):
    async def notify(self, user_id: str, kind: str, message: str) -> None:
        """Best-effort user notification (reconnect needed, order placed, etc.)."""
        ...
