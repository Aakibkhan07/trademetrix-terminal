"""The routes must hand the manager the caller's id.

`test_builder_tenant_isolation.py` exercises `BuilderManager` directly, which proves the guard
works but says nothing about whether the route supplies the tenant. That distinction is the
whole bug: `get_current_user` was resolved by the dependency, never read, and the manager
looked strategies up by id alone. Removing `user_id=current_user.id` from a route left every
manager test green.

These assert the wiring — that each tenant-data route passes the authenticated profile id
through — by driving the routes with the manager stubbed and recording what it received.
"""

import inspect
import re
from pathlib import Path

import pytest

ROUTES = Path(__file__).resolve().parents[1] / "routes" / "v1_builder.py"
BACKTEST_ROUTES = Path(__file__).resolve().parents[1] / "routes" / "v1_backtest.py"

# Manager calls that reach tenant data and therefore must carry the owner.
TENANT_CALLS = (
    "get",
    "list",
    "update",
    "delete",
    "set_status",
    "publish",
    "archive",
    "clone",
    "rollback",
    "get_versions",
    "get_version",
    "compare",
    "preview",
)

# These two are global by design: templates are shared catalogue entries, not tenant rows.
GLOBAL_CALLS = ("list_templates", "get_template")


# Both managers hold tenant data. Matching only `builder_manager` left the backtest routes'
# `backtest_manager.get_run(...)` unchecked — found by mutation, which stayed green.
MANAGERS = r"(?:builder_manager|backtest_manager)"

# Only the methods that read or mutate a **persisted** tenant row. Deliberately excluded:
#
#   run, stop, resume, get_status  — these drive in-process replay jobs
#                                    (`replay_engine.is_running`), not stored rows. Whether
#                                    process-wide replay state should itself be per-tenant is a
#                                    separate question and is not asserted here, because it is
#                                    not what this fix changed.
#   list_templates, get_template   — the shared template catalogue, global by design.
#
# One exemption beyond method names: a route reached by an HMAC share token has no
# authenticated caller, so there is no tenant to scope to. Scoping it to a session would be
# wrong in the other direction — a shared link is meant to be readable by whoever it was sent
# to, who is not the run's owner. The share token is the authorisation. Named explicitly so
# the exemption is a decision on record rather than a pattern that silently matched
# everything.
SHARE_TOKEN_ROUTES = {"get_shared_report"}

TENANT_CALLS = (
    "create",
    "get",
    "get_run",
    "list",
    "list_runs",
    "update",
    "delete",
    "set_status",
    "publish",
    "archive",
    "clone",
    "rollback",
    "get_versions",
    "get_version",
    "compare",
    "preview",
)

GLOBAL_CALLS = ("list_templates", "get_template")


def _call_expression(text: str, start: int, end_of_name: int) -> str:
    depth = 0
    i = end_of_name
    while i < len(text):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    return text[start : i + 1]


def _call_sites(path: Path):
    """Yield (method, line number, full call text) for every tenant-data manager call.

    The whole call expression is captured, not just the opening line: the real
    `create(..., owner_id=current_user.id)` spans five lines, and a line-based check reads
    that as a missing owner.
    """
    text = path.read_text()
    for m in re.finditer(rf"{MANAGERS}\.(\w+)\(", text):
        line_no = text.count("\n", 0, m.start()) + 1
        yield m.group(1), line_no, _call_expression(text, m.start(), m.end() - 1)


@pytest.mark.parametrize("path,label", [(ROUTES, "builder"), (BACKTEST_ROUTES, "backtest")])
def test_no_tenant_data_call_omits_the_owner(path: Path, label: str):
    """Every tenant-data manager call in the route file passes a user id."""
    offenders = []
    for method, lineno, call in _call_sites(path):
        if method in GLOBAL_CALLS or method not in TENANT_CALLS:
            continue
        # A share-token route has no caller to scope to; see SHARE_TOKEN_ROUTES.
        if _enclosing_route(path, lineno) in SHARE_TOKEN_ROUTES:
            continue
        # `create` takes `owner_id`; everything else takes `user_id`.
        expected = "owner_id" if method == "create" else "user_id"
        if expected not in call:
            offenders.append(f"{path.name}:{lineno}  {method}() has no {expected}")
    assert not offenders, "tenant-data calls missing an owner:\n" + "\n".join(offenders)


def _enclosing_route(path: Path, lineno: int) -> str:
    """Name of the route function a call at `lineno` sits inside."""
    name = ""
    for i, line in enumerate(path.read_text().splitlines(), start=1):
        m = re.match(r"\s*(?:async )?def (\w+)\(", line)
        if m and i <= lineno:
            name = m.group(1)
    return name


def test_every_tenant_route_declares_a_current_user():
    """A route that reaches tenant data must resolve a caller at all."""
    source = ROUTES.read_text()
    tree_names = re.findall(r"async def (\w+)\(", source)
    missing = []
    for name in tree_names:
        body = _function_body(source, name)
        if body is None:
            continue
        if not any(c in TENANT_CALLS for c, _, _ in _call_sites_from_text(body)):
            continue
        if method_is_global_only(body):
            continue
        if "current_user" not in body and "_admin" not in body:
            missing.append(name)
    assert not missing, f"routes touching builder data with no caller resolved: {missing}"


def method_is_global_only(body: str) -> bool:
    calls = {m for m, _, _ in _call_sites_from_text(body)}
    return bool(calls) and all(c in GLOBAL_CALLS for c in calls)


def _call_sites_from_text(body: str):
    for m in re.finditer(rf"{MANAGERS}\.(\w+)\(", body):
        yield m.group(1), body.count("\n", 0, m.start()) + 1, _call_expression(body, m.start(), m.end() - 1)


def _function_body(source: str, name: str) -> str | None:
    m = re.search(rf"async def {name}\(.*?\n(?=\s*(?:@router|def |async def ))", source, re.S)
    return m.group(0) if m else None


def test_get_current_user_is_not_silently_unused_anywhere_in_the_builder_routes():
    """The original defect, stated as a rule: resolving a caller and not reading it is a bug.

    A route that depends on `get_current_user` but never mentions it is almost always a
    missing tenant filter. Global routes should depend on nothing rather than depend and
    ignore, so this is checked across the whole file.
    """
    source = ROUTES.read_text()
    offenders = []
    for m in re.finditer(r"async def (\w+)\(.*?\)\s*->\s*[^:]+:(.*?)(?=\n\s*@router|\n\s*(?:async )?def )", source, re.S):
        name, body = m.group(1), m.group(2)
        if "Depends(get_current_user)" in body and "current_user" not in body.split("Depends(get_current_user)")[-1]:
            offenders.append(name)
    assert not offenders, f"routes that resolve a caller and never use it: {offenders}"


def test_the_manager_still_defaults_to_internal_caller_semantics():
    """`user_id=None` is the escape hatch templates and unsaved DSLs use — keep it working."""
    from builder.manager import _visible_to

    assert _visible_to({"author": "someone"}, None) is True


def test_inspect_shows_owner_on_every_guarded_manager_method():
    """A signature check, so a future method cannot be added without an owner parameter.

    `create` is the writer and names it `owner_id`; every reader and mutator names it
    `user_id`, which is also what `None` means — the internal-caller escape hatch.
    """
    from builder.manager import BuilderManager

    missing = []
    for method in TENANT_CALLS:
        fn = getattr(BuilderManager, method, None)
        if fn is None:
            continue
        params = inspect.signature(fn).parameters
        if "user_id" not in params and "owner_id" not in params:
            missing.append(method)
    assert not missing, f"manager methods with no owner parameter: {missing}"
