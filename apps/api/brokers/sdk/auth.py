"""Unified broker authentication layer (SDK v2 Phase 3).

A broker-agnostic token/session lifecycle: expiry detection, automatic
refresh (single-flight), re-auth state, session health, multi-account
support and a pluggable secure storage abstraction (``TokenStore``).  Broker
behaviour lives in provider classes (``AuthProvider`` subclasses) — never in
branching inside this module.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from brokers.sdk.events import AuditEventBus, BrokerEventKind, audit_bus

logger = logging.getLogger("brokers.sdk.auth")

TOKEN_EXPIRY_BUFFER_SECONDS = 300  # consider a token expiring 5 min early


@dataclass
class Token:
    """An access token carried around the lifecycle."""

    access_token: str
    refresh_token: str = ""
    expires_at: float | None = None        # epoch seconds (None = no expiry)
    token_type: str = "bearer"
    scopes: str = ""
    issuer: str = ""                       # "oauth" | "api_key" | "access_token"
    client_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class TokenState(Enum):
    VALID = "valid"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"
    INVALID = "invalid"


class AuthState(Enum):
    """Lifecycle state of a managed session (surfaced in health)."""

    ANONYMOUS = "anonymous"
    AUTHENTICATING = "authenticating"
    AUTHENTICATED = "authenticated"
    EXPIRED = "expired"
    REAUTH_REQUIRED = "reauth_required"
    REFRESH_FAILED = "refresh_failed"


class ReAuthRequiredError(Exception):
    """Raised when no refresh token exists and the session must be re-consented."""

    def __init__(self, message: str = "Broker re-authentication required"):
        super().__init__(message)
        self.reason = message


def token_state(token: Token, buffer_seconds: float = TOKEN_EXPIRY_BUFFER_SECONDS) -> TokenState:
    if not token or not token.access_token:
        return TokenState.INVALID
    if token.expires_at is None:
        return TokenState.VALID
    now = time.time()
    if token.expires_at <= now:
        return TokenState.EXPIRED
    if token.expires_at - now <= buffer_seconds:
        return TokenState.EXPIRING_SOON
    return TokenState.VALID


def seconds_to_expiry(token: Token, now: float | None = None) -> float:
    if token.expires_at is None:
        return float("inf")
    return token.expires_at - (now or time.time())


# ---------------------------------------------------------------------------
# Secure storage abstraction
# ---------------------------------------------------------------------------


class TokenStore(ABC):
    """Persist/load opaque token blobs under a stable key.

    Implementations decide the security model: Supabase (encrypted columns),
    Redis, or memory for tests.  Key shape is opaque to callers, e.g.
    ``user:<user_id>:broker:<broker>``.
    """

    @abstractmethod
    def load(self, key: str) -> Token | None: ...

    @abstractmethod
    def save(self, key: str, token: Token) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...


class InMemoryTokenStore(TokenStore):
    """Process-local store (tests, single-instance deploys)."""

    def __init__(self):
        self._data: dict[str, Token] = {}
        self._lock = threading.Lock()

    def load(self, key: str) -> Token | None:
        with self._lock:
            return self._data.get(key)

    def save(self, key: str, token: Token) -> None:
        with self._lock:
            self._data[key] = token

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)


class RedisTokenStore(TokenStore):
    """Redis-backed store (shared across workers).  Lazily imports Redis."""

    KEY_PREFIX = "broker:token:v1:"

    @staticmethod
    def _redis():
        from core.cache import get_redis

        return get_redis()

    def load(self, key: str) -> Token | None:
        try:
            raw = self._redis().get(f"{self.KEY_PREFIX}{key}")
        except Exception:
            logger.warning("Redis token load failed for %s", key)
            return None
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return Token(**data)
        except (ValueError, TypeError, json.JSONDecodeError):
            return None

    def save(self, key: str, token: Token) -> None:
        try:
            self._redis().set(f"{self.KEY_PREFIX}{key}", json.dumps(_token_to_dict(token)))
        except Exception:
            logger.warning("Redis token save failed for %s", key)

    def delete(self, key: str) -> None:
        try:
            self._redis().delete(f"{self.KEY_PREFIX}{key}")
        except Exception:
            pass


def _token_to_dict(token: Token) -> dict[str, Any]:
    return {
        "access_token": token.access_token,
        "refresh_token": token.refresh_token,
        "expires_at": token.expires_at,
        "token_type": token.token_type,
        "scopes": token.scopes,
        "issuer": token.issuer,
        "client_id": token.client_id,
        "metadata": token.metadata,
    }


def _token_from_dict(data: dict[str, Any]) -> Token:
    return Token(
        access_token=data.get("access_token", ""),
        refresh_token=data.get("refresh_token", ""),
        expires_at=data.get("expires_at"),
        token_type=data.get("token_type", "bearer"),
        scopes=data.get("scopes", ""),
        issuer=data.get("issuer", ""),
        client_id=data.get("client_id", ""),
        metadata=data.get("metadata", {}) or {},
    )


# ---------------------------------------------------------------------------
# Broker provider abstraction
# ---------------------------------------------------------------------------


class AuthProvider(ABC):
    """Broker-specific auth behavior. One subclass per broker — no branching."""

    broker: str = ""

    @abstractmethod
    async def login(self, credentials: dict[str, Any]) -> Token:
        """Exchange credentials (incl. OAuth auth-code) for a fresh Token."""

    async def refresh(self, token: Token) -> Token:
        """Refresh a token. Default: no silent refresh -> require re-auth."""
        raise ReAuthRequiredError(f"{self.broker} token requires re-authentication")

    async def validate(self, token: Token) -> bool:
        """Token validity beyond expiry (e.g. revocation). Default = expiry only."""
        return token_state(token) == TokenState.VALID

    async def reauth_url(self, user_id: str) -> str | None:
        """Optional URL the user must visit to re-consent (OAuth brokers)."""
        return None


@dataclass
class SessionHealth:
    """Health of one managed session (surfaced by the health service)."""

    broker: str
    account: str
    state: TokenState
    auth_state: AuthState
    ok: bool
    reason: str = ""
    expires_in_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "broker": self.broker,
            "account": self.account,
            "token_state": self.state.value,
            "auth_state": self.auth_state.value,
            "ok": self.ok,
            "reason": self.reason,
            "expires_in_seconds": round(self.expires_in_seconds, 1),
        }


class ManagedSession:
    """A per-(account, broker) session bound to one store + provider."""

    def __init__(
        self,
        account: str,
        provider: AuthProvider,
        store: TokenStore,
        event_bus: AuditEventBus | None = None,
        key_prefix: str = "",
    ):
        self.account = account
        self.provider = provider
        self.store = store
        self.event_bus = event_bus
        self.key = f"{key_prefix}user:{account}:broker:{provider.broker}"
        self._lock = asyncio.Lock()
        self._token: Token | None = None
        self._auth_state = AuthState.ANONYMOUS
        self._last_reason = ""

    def _emit(self, kind: BrokerEventKind, message: str, payload: dict | None = None, severity: str = "info") -> None:
        if self.event_bus is not None:
            self.event_bus.emit(
                kind,
                broker=self.provider.broker,
                account=self.account,
                message=message,
                payload=payload or {},
                severity=severity,
            )

    async def get_token(self, force_login: bool = False) -> Token:
        """Return a valid token, refreshing/login when needed (single-flight)."""
        async with self._lock:
            return await self._get_token_unlocked(force_login)

    async def _get_token_unlocked(self, force_login: bool) -> Token:
        if self._token is None:
            self._token = self.store.load(self.key)
        if not force_login and self._token is not None:
            state = token_state(self._token)
            if state in (TokenState.VALID, TokenState.EXPIRING_SOON):
                self._auth_state = AuthState.AUTHENTICATED
                return self._token
            if state == TokenState.EXPIRED and self._token.refresh_token:
                try:
                    return await self._refresh_and_store(self._token)
                except ReAuthRequiredError:
                    self._auth_state = AuthState.REAUTH_REQUIRED
                    self._last_reason = "refresh unsupported - re-authentication required"
                    self._emit(
                        BrokerEventKind.REAUTH_REQUIRED,
                        f"Re-authentication required for {self.provider.broker}:{self.account}",
                        severity="warning",
                    )
                    raise
        # No stored/valid token -> authenticate (login) up-front.
        try:
            self._auth_state = AuthState.AUTHENTICATING
            token = await self.provider.login(payload_from_previous(self._token))
            self._store_token(token)
            self._token = token
            self._auth_state = AuthState.AUTHENTICATED
            return token
        except ReAuthRequiredError:
            self._auth_state = AuthState.REAUTH_REQUIRED
            self._last_reason = "user consent/authorization required"
            self._emit(
                BrokerEventKind.REAUTH_REQUIRED,
                f"Re-authentication required for {self.provider.broker}:{self.account}",
                severity="warning",
            )
            raise
        except Exception as e:
            self._auth_state = AuthState.REFRESH_FAILED
            self._last_reason = str(e)
            self._emit(
                BrokerEventKind.AUTH_FAILED,
                f"Authentication failed for {self.provider.broker}:{self.account}: {e}",
                payload={"error": str(e)},
                severity="error",
            )
            raise

    async def _refresh_and_store(self, token: Token) -> Token:
        refreshed = await self.provider.refresh(token)
        self._store_token(refreshed)
        self._token = refreshed
        self._auth_state = AuthState.AUTHENTICATED
        self._emit(
            BrokerEventKind.TOKEN_REFRESH,
            f"Token refreshed for {self.provider.broker}:{self.account}",
            payload={"expires_in_seconds": round(seconds_to_expiry(refreshed), 1)},
        )
        return refreshed

    def _store_token(self, token: Token) -> None:
        self.store.save(self.key, token)

    async def invalidate(self) -> None:
        async with self._lock:
            self._token = None
            self.store.delete(self.key)
            self._auth_state = AuthState.ANONYMOUS
            self._emit(BrokerEventKind.TOKEN_EXPIRED, f"Session invalidated for {self.provider.broker}:{self.account}", severity="info")

    def health(self) -> SessionHealth:
        state = token_state(self._token or self.store.load(self.key))
        ok = state in (TokenState.VALID, TokenState.EXPIRING_SOON)
        return SessionHealth(
            broker=self.provider.broker,
            account=self.account,
            state=state,
            auth_state=self._auth_state,
            ok=ok,
            reason=self._last_reason,
            expires_in_seconds=seconds_to_expiry(self._token) if self._token else 0.0,
        )


def payload_from_previous(token: Token | None) -> dict:
    return (token.metadata or {}).get("credentials", {}) if token else {}


class SessionManager:
    """Multi-account registry of :class:`ManagedSession` (keyed user/broker)."""

    def __init__(self, store: TokenStore | None = None, event_bus: AuditEventBus | None = None, key_prefix: str = ""):
        self.store = store or InMemoryTokenStore()
        self.event_bus = event_bus
        self.key_prefix = key_prefix
        self._sessions: dict[str, ManagedSession] = {}
        self._lock = threading.Lock()

    def register(self, account: str, provider: AuthProvider) -> ManagedSession:
        with self._lock:
            key = f"{account}:{provider.broker}"
            session = self._sessions.get(key)
            if session is None:
                session = ManagedSession(
                    account, provider, self.store, event_bus=self.event_bus, key_prefix=self.key_prefix
                )
                self._sessions[key] = session
            return session

    def get(self, account: str, broker: str) -> ManagedSession | None:
        with self._lock:
            return self._sessions.get(f"{account}:{broker}")

    def sessions(self) -> list[ManagedSession]:
        with self._lock:
            return list(self._sessions.values())

    def snapshot(self) -> list[dict[str, Any]]:
        return [s.health().to_dict() for s in self.sessions()]


default_session_manager = SessionManager()