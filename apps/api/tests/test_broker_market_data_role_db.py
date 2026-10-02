"""The market-data-role repository against a real, migrated Postgres.

Every other test of this feature stubs the database. That was the right call while the
schema was still in flux, but it left the one failure mode nobody could see: the queries
select `role`, and `async_safe_single` / `async_safe_execute` swallow every exception and
return `None`. So against a database *without* the column, a role-aware read does not raise
`42703: column broker_credentials.role does not exist` — it returns `None`, and `None` is
what every caller already means by "no broker connected".

That is a silent wrong answer rather than an error, and it is why the migration has to be
applied before the code is deployed: apply it in the wrong order and the UI shows "broker
not connected" for a tenant whose broker is connected perfectly well.

So this file runs the real repository against the real local database and asserts on real
rows. It is skipped when no local Postgres is reachable, because a unit suite that silently
does nothing is worse than one that is visibly absent.

What it pins, in order of how badly a regression would hurt:

* `role` is actually selected and readable — the `42703` case, made visible
* both roles for the same broker coexist for one tenant, and each is addressable
* `resolve_market_data_broker` prefers the market-data row, and **falls back to execution
  when there is no market-data row**, which is the reading that keeps every existing tenant
  working
* `activate_broker` activates within one role without disturbing the other

Credentials are written directly with placeholder ciphertext; nothing here decrypts, and no
broker is ever contacted. Rows are removed on teardown.
"""
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio

DOCKER = "supabase_db_trademetrix-terminal"

#: The local Supabase, from `.env.test`. Loaded here rather than imported from settings on
#: purpose: `apps/api/.env` points at **production** (`*.supabase.co`), and these tests call
#: methods that write — `activate_broker` updates rows. Reading the local stack out of the
#: process configuration would have had a test suite issue UPDATE statements against the
#: live table holding every tenant's broker credentials.
#:
#: It only got away with it because production has no `role` column, so every role-aware
#: query failed first and the write never happened. That is not a safeguard; it is luck with
#: a fuse in it. Hence the guard below as well as the pinned URL.
LOCAL_ENV = Path(__file__).resolve().parents[1] / ".env.test"


def _local_settings() -> tuple[str, str]:
    url = key = ""
    for line in LOCAL_ENV.read_text().splitlines():
        line = line.strip()
        if line.startswith("SUPABASE_URL="):
            url = line.split("=", 1)[1].strip()
        elif line.startswith("SUPABASE_SERVICE_KEY="):
            key = line.split("=", 1)[1].strip()
    return url, key


def _local_supabase_client():
    from supabase import create_client

    url, key = _local_settings()
    return create_client(url, key)


@pytest.fixture(autouse=True)
def _pin_to_the_local_database(monkeypatch):
    """Force every database call in this file at the local stack, and prove it.

    Two separate protections, because either alone has a failure mode:

    * the patch, so `broker_repository.get_supabase()` cannot resolve to the production
      client through `apps/api/.env`;
    * the assertion, so if the patch's target changes — the repository starts importing a
      different accessor, say — the file fails here instead of quietly reaching whichever
      database the environment happens to name.
    """
    url, _key = _local_settings()
    assert "localhost" in url or "127.0.0.1" in url, (
        f"refusing to run: .env.test points at {url!r}, which is not a local database"
    )

    import infrastructure.repositories.broker_repository as repo_module

    monkeypatch.setattr(repo_module, "get_supabase", _local_supabase_client)

    client = repo_module.get_supabase()
    # Two traps in one line, both of which turned this guard into an error instead of a
    # check: the attribute is `supabase_url` (`base_url` does not exist on this client), and
    # it holds a `yarl.URL`, not a `str`, so `in` raises TypeError rather than answering the
    # question. A guard that errors is a guard nobody reads the message of.
    resolved = str(client.supabase_url)
    assert "localhost" in resolved or "127.0.0.1" in resolved, (
        f"the client under test resolved to {resolved!r} — refusing to write there"
    )
    return client


def _psql(sql: str) -> str:
    """Run SQL against the local database. Returns stdout; raises on a psql error.

    The stderr is folded into the exception on purpose. `check=True` alone reports
    "returned non-zero exit status 1" and hides the actual reason — which on a failed
    INSERT is a foreign-key violation naming a column you did not know was constrained.
    That cost a debugging round trip while writing this file, and it is the kind of thing
    that gets misread as "the test is wrong".
    """
    import subprocess

    proc = subprocess.run(
        ["docker", "exec", "-i", DOCKER, "psql", "-U", "postgres", "-d", "postgres",
         "-v", "ON_ERROR_STOP=1", "-tAc", sql],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"psql failed ({proc.returncode})\nSQL: {sql}\n{proc.stderr.strip()}"
        )
    return proc.stdout.strip()


def _local_database_reachable() -> bool:
    """True when the local Postgres answers a trivial query.

    Only the *reachability* of the database is a skip condition. Whether the migration has
    been applied is not, and conflating the two was a bug this file shipped with: an earlier
    version skipped on "no database **or** no `role` column", which meant that dropping the
    column turned all six tests into skips — including
    `test_the_role_column_is_readable_not_silently_absent`, the one test whose entire
    purpose is to fail when the column is missing. Dropping the column and watching the file
    go quietly green is precisely the failure it was written to catch.

    So an un-migrated database has to fail here, loudly.
    """
    import subprocess

    try:
        out = subprocess.run(
            ["docker", "exec", DOCKER, "psql", "-U", "postgres", "-d", "postgres", "-tAc", "SELECT 1;"],
            capture_output=True, text=True, timeout=20,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return False
    return out.returncode == 0 and out.stdout.strip() == "1"


def _assert_migration_applied() -> None:
    """Fail, loudly and specifically, when the schema is behind the code.

    Raised from an autouse fixture rather than folded into the skipif, so that "no database"
    skips and "database without the migration" fails. The message says which of the two the
    reader is looking at, because the symptom in the application is neither — it is an
    indistinguishable "broker not connected".
    """
    import subprocess

    out = subprocess.run(
        ["docker", "exec", DOCKER, "psql", "-U", "postgres", "-d", "postgres", "-tAc",
         "SELECT count(*) FROM information_schema.columns "
         "WHERE table_name='broker_credentials' AND column_name='role';"],
        capture_output=True, text=True, timeout=20,
    )
    assert out.stdout.strip() == "1", (
        "supabase/migrations/20261002_01000_broker_credentials_market_data_role.sql has not "
        "been applied to the local database. This is not a flaky-test situation and not "
        "something to skip: role-aware reads fail with 42703, core.safe_query swallows it, "
        "and every caller reads 'no broker connected' for a tenant that is connected. "
        "Apply the migration, then re-run."
    )


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not _local_database_reachable(), reason="no local Postgres reachable"),
]


@pytest.fixture(autouse=True)
def _schema_is_migrated():
    _assert_migration_applied()


@pytest.fixture
async def tenant():
    """A fully isolated throwaway tenant.

    Created by inserting into `auth.users`, whose trigger creates the `profiles` row. That
    matters: `broker_credentials.user_id` references `profiles.id`, and `profiles.id`
    references `auth.users.id`, so a tenant cannot be fabricated by inserting into
    `profiles` — and borrowing an existing profile was the alternative, which is worse than
    it looks. `resolve_market_data_broker` reads *every* active credential for the user, so
    a borrowed profile carrying real credentials would make these assertions depend on
    whoever happens to be first in the table.

    Teardown removes the credentials and then the auth user, which cascades to the profile.
    """
    user_id = str(uuid.uuid4())
    tag = user_id
    _psql(
        "INSERT INTO auth.users (instance_id, id, aud, role, email, encrypted_password, "
        "email_confirmed_at, raw_app_meta_data, raw_user_meta_data, created_at, updated_at) "
        "VALUES ('00000000-0000-0000-0000-000000000000', "
        f"'{user_id}', 'authenticated', 'authenticated', '{user_id}@example.com', "
        "crypt('not-a-real-password', gen_salt('bf')), now(), "
        "'{\"provider\":\"email\",\"providers\":[\"email\"]}', '{}', now(), now());"
    )
    assert _psql(f"SELECT count(*) FROM profiles WHERE id = '{user_id}';") == "1", (
        "the auth.users trigger did not create a profile row; the fixture cannot work"
    )

    try:
        yield user_id
    finally:
        _psql(f"DELETE FROM broker_credentials WHERE user_id = '{user_id}';")
        _psql(f"DELETE FROM auth.users WHERE id = '{user_id}';")


def _insert(user_id: str, broker: str, role: str | None, tag: str) -> None:
    """Write a credential row with recognisable placeholder ciphertext."""
    role_sql = f"'{role}'" if role else "NULL"  # NULL -> column DEFAULT applies
    _psql(
        "INSERT INTO broker_credentials "
        "(user_id, broker, encrypted_api_key, encrypted_secret_key, is_active, role) "
        f"VALUES ('{user_id}', '{broker}', 'test-{tag}', 'test-{tag}', true, {role_sql});"
    )


def _roles_seen(user_id: str) -> dict[str, str]:
    out = _psql(
        "SELECT role, encrypted_api_key FROM broker_credentials "
        f"WHERE encrypted_api_key LIKE 'test-%' AND user_id = '{user_id}' ORDER BY role;"
    )
    return dict(
        line.split("|") for line in out.splitlines() if "|" in line
    )


async def test_the_role_column_is_readable_not_silently_absent(tenant):
    """The `42703` case, stated as a test.

    Without the migration this select fails, `async_safe_execute` swallows it, and the
    repository reports "no credential" for a tenant that has one. Here it must succeed and
    return the row.
    """
    from infrastructure.repositories.broker_repository import SupabaseBrokerRepository

    repo = SupabaseBrokerRepository()

    _insert(tenant, "fyers", "execution", "exec")

    row = await repo.get_by_user_and_broker(tenant, "fyers", role="execution")

    assert row is not None, (
        "repository returned None for a credential that exists — the role column is "
        "probably not applied, and the error is being swallowed by async_safe_execute"
    )
    assert row.role == "execution"


async def test_both_roles_coexist_and_are_separately_addressable(tenant):
    """The capability the migration bought: one broker, two roles, one tenant."""
    from infrastructure.repositories.broker_repository import SupabaseBrokerRepository

    repo = SupabaseBrokerRepository()

    _insert(tenant, "fyers", "execution", "exec")
    _insert(tenant, "fyers", "market_data", "md")

    execution = await repo.get_by_user_and_broker(tenant, "fyers", role="execution")
    market_data = await repo.get_by_user_and_broker(tenant, "fyers", role="market_data")

    assert execution is not None and market_data is not None
    assert execution.id != market_data.id, "both roles resolved to the same row"


async def test_market_data_broker_prefers_the_market_data_role(tenant):
    """A tenant with a dedicated market-data row gets that broker for prices."""
    from infrastructure.repositories.broker_repository import SupabaseBrokerRepository

    repo = SupabaseBrokerRepository()

    _insert(tenant, "fyers", "execution", "exec")
    _insert(tenant, "dhan", "market_data", "md")

    assert await repo.resolve_market_data_broker(tenant) == "dhan"


async def test_market_data_broker_falls_back_to_the_execution_credential(tenant):
    """The fallback every existing tenant depends on.

    No market-data row means "price through the broker that also places your orders", never
    "no prices". Getting this backwards would blank out quotes for all 31 tenants that have
    no market-data credential, so it is asserted in both directions: present, and absent.
    """
    from infrastructure.repositories.broker_repository import SupabaseBrokerRepository

    repo = SupabaseBrokerRepository()

    _insert(tenant, "fyers", "execution", "exec")
    assert await repo.resolve_market_data_broker(tenant) == "fyers"

    # With an explicitly inactive execution row and no market-data row there is nothing to
    # price through, and returning None is correct — the point is that it does not fall
    # back to *some other* broker.
    _psql(
        f"UPDATE broker_credentials SET is_active = false "
        f"WHERE user_id = '{tenant}' AND encrypted_api_key LIKE 'test-%';"
    )
    assert await repo.resolve_market_data_broker(tenant) is None


async def test_activate_within_one_role_leaves_the_other_alone(tenant):
    """Activating a market-data credential must not deactivate the execution one.

    Before roles existed `activate_broker` deactivated every *other* broker for the user,
    which is precisely why one credential could not be both. The role scoping has to hold,
    or connecting a data feed would silently break a tenant's ability to trade.
    """
    from infrastructure.repositories.broker_repository import SupabaseBrokerRepository

    repo = SupabaseBrokerRepository()

    _insert(tenant, "fyers", "execution", "exec")
    _insert(tenant, "dhan", "market_data", "md")

    assert await repo.activate_broker(tenant, "dhan", role="market_data") is True

    rows = _psql(
        "SELECT role || '|' || is_active FROM broker_credentials "
        f"WHERE user_id = '{tenant}' AND encrypted_api_key LIKE 'test-%' ORDER BY role;"
    )
    # psql's text output renders booleans as `true`, not `t`.
    state = dict(line.split("|") for line in rows.splitlines() if "|" in line)
    assert state["market_data"] == "true"
    assert state["execution"] == "true", (
        "activating the market-data credential deactivated the execution one"
    )


async def test_an_unknown_role_is_rejected_before_it_reaches_the_database(tenant):
    """Fail at the boundary, not at the constraint.

    `_check_role` exists so a typo becomes a clear error at the call site. Letting it reach
    Postgres would surface a generic 23514 and lose the role name's origin.
    """
    from infrastructure.repositories.broker_repository import SupabaseBrokerRepository

    repo = SupabaseBrokerRepository()

    with pytest.raises(ValueError):
        await repo.activate_broker(tenant, "fyers", role="marketdata")
