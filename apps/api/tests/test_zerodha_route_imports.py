"""The Zerodha routes resolve `httpx` from module scope, not from a local import.

These three routes had no test at all, which made a routine lint cleanup unanswerable by
running the suite. `ruff --fix` removed a function-local `import httpx` from two of them as
an unused import, which looked safe — and was, but only because `httpx` is already imported
at module level. Had that module-level import ever been removed, or had these functions been
moved, the same edit would have left `httpx.Timeout(...)` with no binding and produced a
`NameError` on a live auth path. A green suite would not have mentioned it.

So the reasoning is pinned here rather than left in a commit message:

* the module-level import is what the routes depend on, and
* the exact expression each route evaluates resolves without a local import.

The broker paths are genuinely exercised elsewhere, but "exercised elsewhere" is not a
substitute for the import that was just deleted being real. If this file starts failing
after a lint run, read it before assuming the suite is wrong.
"""
import pytest

from core.config import settings


def test_httpx_is_bound_at_module_scope():
    """The precondition the routes rely on, stated directly."""
    import routes.v1_brokers as v1_brokers

    assert "httpx" in v1_brokers.__dict__, (
        "routes/v1_brokers.py references httpx but does not import it at module level; "
        "the function-local imports were removed as redundant, so this is now the only binding"
    )


@pytest.mark.parametrize(
    "route_name",
    ["zerodha_login_url", "zerodha_exchange_request_token", "zerodha_callback"],
)
def test_each_route_can_reach_httpx(route_name):
    """Resolve the name the way the route body will at call time.

    `fn.__globals__` is the module namespace, which is what an unqualified `httpx.Timeout`
    inside the function actually binds to. Checking the function's globals rather than
    importing `httpx` in this test is the point: the test must fail if the route's module
    stops providing it, even though this test file is perfectly happy.
    """
    import routes.v1_brokers as v1_brokers

    fn = getattr(v1_brokers, route_name)
    assert "httpx" in fn.__globals__, f"{route_name} has no httpx binding at call time"

    timeout = fn.__globals__["httpx"].Timeout(
        settings.broker_request_timeout, connect=settings.broker_connect_timeout
    )
    # A meaningful value, not just "did not raise": the timeout is part of what these auth
    # calls depend on, and a silently-defaulted one would hang a broker login.
    assert timeout.read > 0
    assert timeout.connect > 0


def test_all_three_zerodha_routes_are_registered():
    """They exist at all — the cheapest possible smoke test for routes nothing covers."""
    import routes.v1_brokers as v1_brokers

    paths = {r.path for r in v1_brokers.router.routes}
    assert "/brokers/zerodha/login-url" in paths
    assert "/brokers/zerodha/exchange-request-token" in paths
    assert "/brokers/zerodha/callback" in paths
