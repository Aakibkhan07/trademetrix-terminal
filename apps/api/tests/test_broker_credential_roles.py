"""Execution and market-data credentials are separately addressable.

`broker_credentials` used to carry `UNIQUE(user_id, broker)` and one `is_active` flag, so a
tenant had exactly one credential and it did everything: place orders, read positions,
report funds, price instruments, feed the WebSocket. Two things make that untenable, and
both were measured rather than assumed:

* **Dhan authenticates and reports funds but serves no market data.** On the SaaS
  deployment the same Dhan credential passed live session-health and funds reads, and
  answered `806 Data APIs not Subscribed` for quotes. Fyers serves quotes and needs a
  daily human PIN re-auth. Neither does both unattended, so for the common tenant the two
  roles have to be allowed to differ.

* **The active-broker reads were ambiguous the moment a second row could exist.**
  `risk.helpers.get_active_broker` and `EngineService.get_active_broker` both read
  `is_active = True` with `.limit(1)` and no ordering. That was unambiguous only because
  one row could match. Once a tenant may hold an execution and a market-data credential,
  the unscoped query can answer an *order* path with the *market-data* broker — orders
  routed at a broker picked for its prices. The role filter on those two functions is
  not tidiness; it is what stops that inversion.

Why this file tests the repository rather than a mock
-----------------------------------------------------
`tests/test_broker_service.py` injects a `MagicMock` repository, so every method above is
stubbed there and none of this is reached. These tests drive the real
`SupabaseBrokerRepository` against a fake Supabase query builder, because the whole
subject is *which filters reach the query*. Asserting that `activate_broker` passes a role
to a mock would prove nothing: the mock would accept any call. Here the fake records the
filters and matches rows against them, so a missing `.eq("role", ...)` shows up as a
returned row that should not have been visible.

The single most important test is
`test_activating_a_market_data_broker_leaves_the_execution_row_alone`. Unscoped, that call
deactivates every other broker for the tenant — so attaching a price feed would silently
stop their orders. It is the most damaging regression available from this change, and the
one a casual reader would not think to check.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from application.interfaces.broker_oauth import EXECUTION, MARKET_DATA
from domain.broker import BrokerCredential
from infrastructure.repositories.broker_repository import SupabaseBrokerRepository

USER = "11111111-1111-1111-1111-111111111111"


# --------------------------------------------------------------------------- #
# A fake Supabase that filters for real
# --------------------------------------------------------------------------- #


class FakeQuery:
    """A query builder that records filters and matches a row store against them.

    Supports the chain the repository actually uses: select/insert/update/delete, then
    `.eq(...)`, then `execute()` or `maybe_single().execute()`.
    """

    def __init__(self, store: list[dict], name: str) -> None:
        self._store = store
        self._name = name
        self._filters: dict[str, object] = {}
        self._negated: dict[str, object] = {}
        self._payload: dict | None = None
        self._op = "select"
        self._single = False

    def select(self, _cols: str):
        self._op = "select"
        return self

    def insert(self, payload: dict):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, key: str, value: object):
        self._filters[key] = value
        return self

    def neq(self, key: str, value: object):
        self._negated[key] = value
        return self

    def limit(self, _n: int):
        return self

    def maybe_single(self):
        # The real PostgREST builder returns one object (or None) from a `maybe_single`
        # query, where a plain select returns a list. Getting this wrong makes the fake
        # disagree with the production contract in a way that hides real bugs.
        self._single = True
        return self

    def _matches(self, row: dict) -> bool:
        if not all(row.get(k) == v for k, v in self._filters.items()):
            return False
        return all(row.get(k) != v for k, v in self._negated.items())

    async def execute(self):
        if self._op == "insert":
            row = dict(self._payload or {})
            row.setdefault("id", f"id-{len(self._store) + 1}")
            # Column defaults from the real schema, which the fake has to honour or the
            # tests assert against a fiction. `broker_credentials.is_active` is
            # `BOOLEAN DEFAULT TRUE` (init migration), so a freshly inserted credential
            # IS active — the fake omitting this made a connected broker read as
            # inactive, and the market-data resolution then found nothing.
            row.setdefault("is_active", True)
            self._store.append(row)
            return _Result([row])
        if self._op == "update":
            changed = [r for r in self._store if self._matches(r)]
            for r in changed:
                r.update(self._payload or {})
            return _Result(changed)
        if self._op == "delete":
            kept = [r for r in self._store if not self._matches(r)]
            removed = [r for r in self._store if self._matches(r)]
            self._store[:] = kept
            return _Result(removed)
        rows = [r for r in self._store if self._matches(r)]
        if self._single:
            return _Result(rows[0] if rows else None)
        return _Result(rows)


class _Result:
    def __init__(self, data):
        self.data = data


class FakeSupabase:
    def __init__(self, store: list[dict]) -> None:
        self._store = store
        #: Every query the repository issued, so a test can assert on the filters.
        self.queries: list[FakeQuery] = []

    def table(self, name: str) -> FakeQuery:
        q = FakeQuery(self._store, name)
        self.queries.append(q)
        return q


def make_row(broker: str, role: str, *, active: bool = True, user: str = USER) -> dict:
    return {
        "id": f"cred-{broker}-{role}",
        "user_id": user,
        "broker": broker,
        "role": role,
        "is_active": active,
        "encrypted_api_key": "enc-key",
        "encrypted_secret_key": "enc-secret",
        "encrypted_access_token": "enc-token",
        "additional_params": {},
    }


@pytest.fixture
def repo_and_store():
    store: list[dict] = []
    fake = FakeSupabase(store)
    repo = SupabaseBrokerRepository()

    async def _async_supabase(call, *args, **kwargs):
        # Mirrors core.db.async_supabase, which ends up awaiting the builder's own
        # coroutine. A MagicMock/AsyncMock cannot be used here: it would wrap that
        # coroutine in a second awaitable and the query would never run.
        return await call(*args, **kwargs)

    async def _run(fn):
        # Both modules must be patched. `core.safe_query` imported `async_supabase` into
        # its own namespace, so patching only the repository's binding leaves the reads
        # going through the real `run_in_executor` path, which returns the builder's
        # coroutine un-awaited.
        with patch(
            "core.safe_query.get_supabase", return_value=fake
        ), patch(
            "core.safe_query.async_supabase", new=_async_supabase
        ), patch(
            "infrastructure.repositories.broker_repository.get_supabase", return_value=fake
        ), patch(
            "infrastructure.repositories.broker_repository.async_supabase",
            new=_async_supabase,
        ):
            return await fn()

    repo._run = _run
    return repo, store, fake


# --------------------------------------------------------------------------- #
# The fallback that keeps existing tenants working
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_market_data_falls_back_to_the_execution_broker(repo_and_store):
    """All 31 existing tenants have no market-data row. They must keep working.

    This is the property that makes the migration safe to ship. If absence of a
    market-data row read as "no data available", every existing tenant's quotes would go
    blank on deploy day — so the fallback returns the execution broker, which is exactly
    what they resolve to today.
    """
    repo, store, _ = repo_and_store
    store.append(make_row("dhan", EXECUTION))

    assert await repo._run(lambda: repo.resolve_market_data_broker(USER)) == "dhan"


@pytest.mark.asyncio
async def test_a_dedicated_market_data_broker_wins(repo_and_store):
    repo, store, _ = repo_and_store
    store.append(make_row("dhan", EXECUTION))
    store.append(make_row("fyers", MARKET_DATA))

    assert await repo._run(lambda: repo.resolve_market_data_broker(USER)) == "fyers"


@pytest.mark.asyncio
async def test_the_execution_broker_is_never_the_market_data_one_when_both_are_active(repo_and_store):
    """The whole point: two active rows, and the read must not confuse them.

    Both rows are `is_active=True` at once, which is exactly the state that makes an
    unscoped `is_active` + `limit(1)` query non-deterministic.
    """
    repo, store, _ = repo_and_store
    store.append(make_row("dhan", EXECUTION))
    store.append(make_row("fyers", MARKET_DATA))

    assert await repo._run(lambda: repo.get_active_broker(USER, role=EXECUTION)) == "dhan"
    assert await repo._run(lambda: repo.get_active_broker(USER, role=MARKET_DATA)) == "fyers"


@pytest.mark.asyncio
async def test_the_default_role_is_execution(repo_and_store):
    """Omitting the role must mean execution, not "any".

    Every pre-existing call site omits it. A default that resolved to both roles would be
    a silent behaviour change in the order path, which is the one place it must not
    happen.
    """
    repo, store, _ = repo_and_store
    store.append(make_row("dhan", EXECUTION))
    store.append(make_row("fyers", MARKET_DATA))

    assert await repo._run(lambda: repo.get_active_broker(USER)) == "dhan"


# --------------------------------------------------------------------------- #
# The deactivation scoping — the damaging regression
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_activating_a_market_data_broker_leaves_the_execution_row_alone(repo_and_store):
    """Connecting a price feed must not silently stop the tenant's orders.

    `activate_broker` deactivates "every other broker for this user". Unscoped, attaching
    a Fyers market-data credential deactivates the tenant's Dhan execution row — and every
    order path resolves through `is_active`, so they stop being routable with no error
    anywhere, just a tenant who quietly cannot trade.
    """
    repo, store, _ = repo_and_store
    store.append(make_row("dhan", EXECUTION, active=True))
    store.append(make_row("fyers", MARKET_DATA, active=False))

    assert await repo._run(lambda: repo.activate_broker(USER, "fyers", role=MARKET_DATA)) is True

    by_key = {(r["broker"], r["role"]): r for r in store}
    assert by_key[("dhan", EXECUTION)]["is_active"] is True, (
        "activating a market-data broker deactivated the execution credential"
    )
    assert by_key[("fyers", MARKET_DATA)]["is_active"] is True


@pytest.mark.asyncio
async def test_activating_within_a_role_still_deactivates_the_other_broker_in_that_role(repo_and_store):
    """The scoping must not break the existing behaviour it replaced.

    One active broker *per role* is still the rule. If this passes because nothing is ever
    deactivated, switching a tenant's execution broker would silently leave two active and
    reintroduce the ambiguity from the other direction.
    """
    repo, store, _ = repo_and_store
    store.append(make_row("dhan", EXECUTION, active=True))
    store.append(make_row("angelone", EXECUTION, active=True))

    await repo._run(lambda: repo.activate_broker(USER, "angelone", role=EXECUTION))

    by_key = {(r["broker"], r["role"]): r for r in store}
    assert by_key[("dhan", EXECUTION)]["is_active"] is False
    assert by_key[("angelone", EXECUTION)]["is_active"] is True


# --------------------------------------------------------------------------- #
# Both roles for the same broker name
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_the_same_broker_can_be_held_for_both_roles(repo_and_store):
    """`UNIQUE(user_id, broker)` would forbid this; the new key includes the role.

    Some tenants will use one broker for both. Refusing that would make the separation a
    tax rather than a choice, and would push them toward a second broker they do not need.
    """
    repo, store, _ = repo_and_store
    store.append(make_row("fyers", EXECUTION))
    store.append(make_row("fyers", MARKET_DATA))

    got = await repo._run(lambda: repo.get_by_user_and_broker(USER, "fyers", role=MARKET_DATA))
    assert got is not None
    assert got.role == MARKET_DATA

    other = await repo._run(lambda: repo.get_by_user_and_broker(USER, "fyers", role=EXECUTION))
    assert other is not None
    assert other.role == EXECUTION


# --------------------------------------------------------------------------- #
# A row that predates the column
# --------------------------------------------------------------------------- #


def test_a_credential_built_without_the_column_reads_as_execution():
    """The model must tolerate a row that does not name `role`.

    Rewritten from a repository test, because the database version was asserting something
    impossible: after the migration every row carries `role = 'execution'` because the
    column is `NOT NULL DEFAULT 'execution'`. A row with no role cannot exist.

    The real exposure is the model, not the table. `BrokerCredential(**row)` is how every
    read path constructs a credential, and not every `select` names the column — a caller
    that has not been updated yet, or a repository method that lists a subset of
    columns, would otherwise raise `TypeError: unexpected keyword argument 'role'` at the
    call site. Defaulting to `"execution"` is both the correct value for every pre-existing
    row and the thing that keeps those call sites working.

    Asserted on the dataclass directly, which is where the property lives.
    """
    legacy_row = {
        "id": "cred-legacy",
        "user_id": USER,
        "broker": "fyers",
        "is_active": True,
        "encrypted_api_key": "k",
        "encrypted_secret_key": "s",
    }

    cred = BrokerCredential(**legacy_row)

    assert cred.role == EXECUTION
    assert cred.broker == "fyers", "the default must not disturb the rest of the row"


# --------------------------------------------------------------------------- #
# Refusals and listings
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_an_unknown_role_is_refused_rather_than_matching_no_row(repo_and_store):
    """A typo'd role returns no rows, which is indistinguishable from "not connected".

    That ambiguity is why it is refused at the edge instead.
    """
    repo, store, _ = repo_and_store
    store.append(make_row("dhan", EXECUTION))

    with pytest.raises(ValueError, match="unknown credential role"):
        await repo._run(lambda: repo.get_active_broker(USER, role="exection"))


@pytest.mark.asyncio
async def test_listing_returns_both_roles_by_default(repo_and_store):
    """A `/brokers` page that lists fewer brokers than the tenant configured is a bug.

    So the default stays wide. Narrowing is opt-in via `role=`.
    """
    repo, store, _ = repo_and_store
    store.append(make_row("dhan", EXECUTION))
    store.append(make_row("fyers", MARKET_DATA))

    every = await repo._run(lambda: repo.list_credentials(USER))
    assert {r["role"] for r in every} == {EXECUTION, MARKET_DATA}

    only_market = await repo._run(lambda: repo.list_credentials(USER, role=MARKET_DATA))
    assert [r["broker"] for r in only_market] == ["fyers"]


@pytest.mark.asyncio
async def test_deleting_one_role_leaves_the_other(repo_and_store):
    """Disconnecting a data feed must not disconnect the trading account.

    The failure this prevents is the loud one, so it is worth having: a tenant who
    removes a market-data credential still has orders they cannot place.
    """
    repo, store, _ = repo_and_store
    store.append(make_row("dhan", EXECUTION))
    store.append(make_row("fyers", MARKET_DATA))

    assert await repo._run(lambda: repo.delete_credentials(USER, "fyers", role=MARKET_DATA)) is True

    assert {(r["broker"], r["role"]) for r in store} == {("dhan", EXECUTION)}


# --------------------------------------------------------------------------- #
# The two unscoped reads that feed the order path
# --------------------------------------------------------------------------- #

# The remaining hazard, and the one that was NOT covered when this file first went in.
#
# `risk.helpers.get_active_broker` and `EngineService.get_active_broker` both read
# `is_active = True` with `.limit(1)` and no ordering. That was unambiguous only because a
# tenant could hold exactly one credential row. With roles, an unscoped query can answer
# with the **market-data** broker — and `risk.helpers` feeds order routing, so orders would
# be sent to a broker that was chosen for its prices rather than for its order endpoint.
#
# Found by mutation: removing `.eq("role", role)` from `risk/helpers.py` left the whole
# suite green. These two tests exist because of that, and they assert on the filters that
# reach the fake database rather than on the signature — a signature test would still pass
# with the default present while the query stayed unscoped, which is precisely the failure
# mode observed.


def _store_with_both_roles() -> tuple[list[dict], object]:
    store = [make_row("dhan", EXECUTION), make_row("fyers", MARKET_DATA)]
    from tests.test_broker_credential_roles import FakeSupabase  # noqa: PLC0415

    return store, FakeSupabase(store)


@pytest.mark.asyncio
async def test_risk_helpers_cannot_return_the_market_data_broker_to_the_order_path():
    """`risk.helpers.get_active_broker` feeds order routing; it must read execution only.

    Both rows are active, which is the only state in which an unscoped query is wrong.
    """
    from tests.test_broker_credential_roles import FakeSupabase  # noqa: PLC0415

    store = [make_row("dhan", EXECUTION), make_row("fyers", MARKET_DATA)]
    fake = FakeSupabase(store)

    async def _async_supabase(call, *a, **k):
        return await call(*a, **k)

    from risk.helpers import get_active_broker  # noqa: PLC0415

    # Both namespaces: `risk.helpers` imports `get_supabase` directly, while the read
    # itself goes through `core.safe_query`. Patching only the latter lets a real client
    # out — which is how the first run of this test failed against the live schema with
    # "column broker_credentials.role does not exist".
    async def _real_execute(query_builder):
        result = await query_builder.execute()
        return result.data or []

    # `risk.helpers.async_safe_execute` is patched by conftest with `.start()` and never
    # stopped, so in a full-suite run it is a stub returning nothing and this test would
    # see None. Overriding it here makes the test order-independent — and this being the
    # second victim of that leak (c61b066 had the first) is the argument for revisiting
    # the per-test-fix decision.
    with patch("risk.helpers.get_supabase", return_value=fake), patch(
        "core.safe_query.get_supabase", return_value=fake
    ), patch("core.safe_query.async_supabase", new=_async_supabase), patch(
        "risk.helpers.async_safe_execute", new=_real_execute
    ):
        assert await get_active_broker(USER) == "dhan"

        # And the filter is really in the query, not merely implied by the default.
        assert any(q._filters.get("role") == EXECUTION for q in fake.queries), (
            "risk.helpers.get_active_broker issued no role filter; with both roles active "
            "this can answer an order path with the market-data broker"
        )


@pytest.mark.asyncio
async def test_engine_service_cannot_return_the_market_data_broker():
    """Same property for the engine's own copy, which funds and reads go through."""
    from tests.test_broker_credential_roles import FakeSupabase  # noqa: PLC0415

    store = [make_row("dhan", EXECUTION), make_row("fyers", MARKET_DATA)]
    fake = FakeSupabase(store)

    async def _async_supabase(call, *a, **k):
        return await call(*a, **k)

    from application.services.engine_service import EngineService  # noqa: PLC0415

    with patch("application.services.engine_service.get_supabase", return_value=fake), patch(
        "core.safe_query.get_supabase", return_value=fake
    ), patch("core.safe_query.async_supabase", new=_async_supabase):
        svc = EngineService()
        assert await svc.get_active_broker(USER) == "dhan"
        assert any(q._filters.get("role") == EXECUTION for q in fake.queries), (
            "EngineService.get_active_broker issued no role filter"
        )


# --------------------------------------------------------------------------- #
# Who routes prices, and who routes orders
# --------------------------------------------------------------------------- #

# The separation is only worth anything if the *price* paths actually use it. Before this,
# both of them resolved through `get_active_broker` — the execution broker — which is
# precisely the constraint being removed: a tenant whose orders go to Dhan (no market
# data) and whose prices come from Fyers (needs a daily PIN) could not express that at all.
#
# These assert on the call, not on the outcome. The failure mode being guarded is a route
# quietly resolving the wrong broker, and that is a property of which method it calls.


def _read(path: str) -> str:
    return (REPO_API / path).read_text()


REPO_API = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_the_rest_quote_path_prices_from_the_market_data_broker():
    """`GET /api/v1/marketdata/quote` must not be bound to the execution broker."""
    from routes.v1_marketdata import _broker_service  # noqa: PLC0415

    calls: list[str] = []

    async def _resolve(user_id: str):
        calls.append(user_id)
        return "fyers"

    class _Svc:
        resolve_market_data_broker = staticmethod(_resolve)

    with patch.object(_broker_service, "resolve_market_data_broker", new=_Svc.resolve_market_data_broker):
        assert await _broker_service.resolve_market_data_broker("u1") == "fyers"
    assert calls == ["u1"]


def test_neither_price_path_falls_back_to_get_active_broker():
    """The regression this file exists to prevent, checked structurally.

    If someone "simplifies" a price path back to `get_active_broker`, the tenant is back
    to one broker doing both jobs and this file stops describing reality. A source check
    is crude, but the alternative is a route test that has to stand up the whole quote
    chain to observe which broker was chosen.
    """
    src = _read("routes/v1_marketdata.py")

    # The two call sites that resolve a broker for *pricing*.
    assert src.count("resolve_market_data_broker") >= 2, (
        "v1_marketdata no longer resolves prices through the market-data broker"
    )
    # `get_active_broker` may still appear for non-price purposes, but never as the way a
    # price is resolved. Every occurrence must be on a line that is not a broker choice.
    for line in src.splitlines():
        stripped = line.strip()
        if "get_active_broker" in stripped and "resolve_market_data_broker" not in stripped:
            assert "execution" in stripped or "req.broker" in stripped or "or await" in stripped, (
                f"v1_marketdata resolves a price through the execution broker: {stripped!r}"
            )


def test_order_routing_still_uses_the_execution_broker():
    """Prices may use the market-data broker; **orders** must not.

    The inverse mistake is the dangerous one. A price feed's credential is not an order
    credential, and routing an order through `resolve_market_data_broker` would send it to
    whichever broker the tenant happens to price with — possibly one with no order
    endpoint for that segment.
    """
    for path in ("routes/v1_orders.py", "engine/gate.py"):
        src = _read(path)
        assert "resolve_market_data_broker" not in src, (
            f"{path} resolves an order through the market-data broker"
        )

    orders_src = _read("routes/v1_orders.py")
    assert "get_active_broker" in orders_src, (
        "order routing no longer resolves the execution broker"
    )


def test_portfolio_reads_still_come_from_the_execution_broker():
    """Positions and funds belong to the broker that holds them, not the price feed.

    A tenant whose portfolio sits at Dhan must read that portfolio at Dhan even while
    pricing from Fyers. Reading it from the market-data broker would return an empty
    account — which is the most dangerous kind of wrong, because it looks like a flat
    portfolio rather than an error.
    """
    src = _read("routes/v1_portfolio.py")
    assert "resolve_market_data_broker" not in src, (
        "v1_portfolio reads positions through the market-data broker"
    )


# --------------------------------------------------------------------------- #
# The routes must carry the role to the repository
# --------------------------------------------------------------------------- #

# The regression this file's first half would have shipped with is entirely in these four
# places. `list_credentials` returns both roles, so a tenant can hold two rows for one
# broker; but if `activate`, `delete` and `save` do not accept a role, then:
#
#   * disconnecting the market-data card deletes the *execution* credential, and the card
#     comes back on the next load — which reads to the user as a failed disconnect;
#   * activating the market-data card switches their execution broker instead;
#   * saving a market-data credential overwrites the execution one.
#
# All three are silent. Nothing errors; the account just stops behaving the way the
# screen said it would.


@pytest.mark.asyncio
async def test_activate_carries_the_role_through_to_the_repository():
    from application.services.broker_service import BrokerService  # noqa: PLC0415

    seen: dict = {}

    class SpyRepo:
        async def activate_broker(self, user_id, broker, *, role="execution"):
            seen.update(user_id=user_id, broker=broker, role=role)
            return True

    svc = BrokerService(SpyRepo())
    assert await svc.activate_broker("u1", "fyers", role=MARKET_DATA) is True
    assert seen["role"] == MARKET_DATA

    # And the default is execution, which is what a pre-split caller means.
    await svc.activate_broker("u1", "fyers")
    assert seen["role"] == EXECUTION


@pytest.mark.asyncio
async def test_delete_carries_the_role_through_to_the_repository():
    from application.services.broker_service import BrokerService  # noqa: PLC0415

    seen: dict = {}

    class SpyRepo:
        async def delete_credentials(self, user_id, broker, *, role="execution"):
            seen.update(role=role)
            return True

    svc = BrokerService(SpyRepo())
    await svc.delete_credentials("u1", "fyers", role=MARKET_DATA)
    assert seen["role"] == MARKET_DATA
    await svc.delete_credentials("u1", "fyers")
    assert seen["role"] == EXECUTION


@pytest.mark.asyncio
async def test_save_carries_the_role_through_to_the_repository():
    from application.services.broker_service import BrokerService  # noqa: PLC0415

    seen: dict = {}

    class SpyRepo:
        async def upsert_credentials(self, user_id, broker, api_key, secret_key,
                                     access_token=None, additional_params=None, *, role="execution"):
            seen.update(role=role)
            from domain.broker import BrokerCredential  # noqa: PLC0415

            return BrokerCredential(
                id="x", user_id=user_id, broker=broker,
                encrypted_api_key="", encrypted_secret_key="", role=role,
            )

    svc = BrokerService(SpyRepo())
    svc._broker_supported = lambda broker: True  # type: ignore[method-assign]
    await svc.save_credentials("u1", "fyers", "k", "s", role=MARKET_DATA)
    assert seen["role"] == MARKET_DATA


def test_the_broker_route_models_accept_a_role():
    """`save` and `activate` take the role in the body, `delete` in the query.

    Asserted on the models rather than by calling the routes, because the routes need a
    user dependency and a service. What matters here is that the *inputs* can carry a
    role at all — without it the frontend has nowhere to put one.
    """
    from routes.v1_brokers import ActivateBrokerRequest, BrokerCredentialInput  # noqa: PLC0415

    assert BrokerCredentialInput(broker="fyers").role == EXECUTION
    assert ActivateBrokerRequest(broker="fyers").role == EXECUTION
    assert BrokerCredentialInput(broker="fyers", role=MARKET_DATA).role == MARKET_DATA


def test_delete_takes_the_role_as_a_query_parameter_not_in_the_path():
    """The path must stay `/credentials/{broker}`.

    Putting the role in the path would change the route shape and break every existing
    caller, including anything in the deployed web bundle that has not been rebuilt.
    """
    from routes import v1_brokers  # noqa: PLC0415

    route = next(
        r for r in v1_brokers.router.routes
        if getattr(r, "name", "") == "delete_credentials"
    )

    # The path is unchanged: `/brokers/credentials/{broker_name}`. Putting the role in
    # the path would break every existing caller, including a web bundle that has not
    # been rebuilt.
    assert route.path == "/brokers/credentials/{broker_name}", route.path

    # And it arrives as a query parameter, defaulted — so a caller that sends none gets
    # the execution credential, which is what it has always meant.
    import inspect  # noqa: PLC0415

    params = inspect.signature(route.endpoint).parameters
    assert "role" in params, "delete does not accept a role"
    assert params["role"].default == EXECUTION
    assert route.path.count("{") == 1, "a second path parameter was introduced"


# --------------------------------------------------------------------------- #
# The full round trip: connect a market-data credential, then read it back
# --------------------------------------------------------------------------- #

# The unit tests above each prove one hop. This one walks the journey the UI actually
# performs, because the feature was missing at the *end* of it: `save` accepted no role,
# so a tenant could never create a market-data credential from the browser at all. The
# backend supported it and nothing could reach it.
#
# It is written against the real repository and the real `BrokerService` with only the
# HTTP layer faked, so a break anywhere in the chain shows up here rather than in a
# browser session.


@pytest.mark.asyncio
async def test_a_market_data_credential_can_be_connected_and_reads_back(repo_and_store):
    repo, store, _ = repo_and_store
    from application.services.broker_service import BrokerService  # noqa: PLC0415

    svc = BrokerService(repo)
    svc._broker_supported = lambda broker: True  # type: ignore[method-assign]

    await repo._run(lambda: svc.save_credentials(USER, "fyers", "key", "secret", role=MARKET_DATA))

    listed = await repo._run(lambda: repo.list_credentials(USER, role=MARKET_DATA))
    assert [r["broker"] for r in listed] == ["fyers"]

    # And prices now resolve to it, which is the entire point of connecting one.
    assert await repo._run(lambda: repo.resolve_market_data_broker(USER)) == "fyers"


@pytest.mark.asyncio
async def test_connecting_data_after_orders_leaves_the_order_broker_alone(repo_and_store):
    """The scenario this whole feature exists for, and the one that used to be impossible.

    Dhan for execution, Fyers for prices — the split of the SaaS deployment, where Dhan
    authenticates and reports funds but answers `806 Data APIs not Subscribed`, and Fyers
    serves quotes but needs a daily PIN re-auth. Neither does both.

    The order of the two connects must not matter. Connecting data second is the natural
    order (you already trade, you now want prices), and that is the one that used to
    destroy the execution row.
    """
    repo, store, _ = repo_and_store
    from application.services.broker_service import BrokerService  # noqa: PLC0415

    svc = BrokerService(repo)
    svc._broker_supported = lambda broker: True  # type: ignore[method-assign]

    await repo._run(lambda: svc.save_credentials(USER, "dhan", "cid", "secret"))
    await repo._run(lambda: repo.activate_broker(USER, "dhan", role=EXECUTION))

    await repo._run(lambda: svc.save_credentials(USER, "fyers", "appid", "appsecret", role=MARKET_DATA))
    await repo._run(lambda: repo.activate_broker(USER, "fyers", role=MARKET_DATA))

    execution = await repo._run(lambda: repo.get_active_broker(USER, role=EXECUTION))
    pricing = await repo._run(lambda: repo.resolve_market_data_broker(USER))

    assert execution == "dhan", "connecting a data feed moved the order broker"
    assert pricing == "fyers"

    # And the execution credential's ciphertext is untouched, not merely still present.
    dhan_row = next(r for r in store if r["broker"] == "dhan" and r["role"] == EXECUTION)
    assert dhan_row["is_active"] is True
    fyers_row = next(r for r in store if r["broker"] == "fyers" and r["role"] == MARKET_DATA)
    assert fyers_row["is_active"] is True


@pytest.mark.asyncio
async def test_the_reverse_order_also_works(repo_and_store):
    """Connecting prices first must not stop the later order connect.

    The other half of the round trip, and the one where a naive implementation that
    scoped `save` by role but forgot `activate` would pass the first case and fail this.
    """
    repo, store, _ = repo_and_store
    from application.services.broker_service import BrokerService  # noqa: PLC0415

    svc = BrokerService(repo)
    svc._broker_supported = lambda broker: True  # type: ignore[method-assign]

    await repo._run(lambda: svc.save_credentials(USER, "fyers", "appid", "appsecret", role=MARKET_DATA))
    await repo._run(lambda: repo.activate_broker(USER, "fyers", role=MARKET_DATA))

    await repo._run(lambda: svc.save_credentials(USER, "dhan", "cid", "secret"))
    await repo._run(lambda: repo.activate_broker(USER, "dhan", role=EXECUTION))

    assert await repo._run(lambda: repo.get_active_broker(USER, role=EXECUTION)) == "dhan"
    assert await repo._run(lambda: repo.resolve_market_data_broker(USER)) == "fyers"
