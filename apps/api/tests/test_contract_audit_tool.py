"""Soundness tests for the contract audit tool.

This tool lives at `apps/web/scripts/audit_api_contracts.py` and is tested from here because the
only Python harness in CI is this suite; adding a second runner for one file is not worth the
configuration. It is loaded by path, so nothing about the API depends on it.

It is tested because **it fabricated twice while being extended**, and both fabrications were
confident, well-formatted and wrong:

1. `find_untyped_declarations` scanned the next 400 characters of text for `method:`. Twelve plain
   `request('/path')` reads — each correctly defaulting to GET — picked up the *following*
   declaration's method and were reported as "client would send POST". A 400-character lookahead is
   not a call boundary; the argument list is.

2. Paths were compared as strings, so the spec's `/brokers/{broker}/exchange-code` became
   `/brokers/*/exchange-code` while the client wrote the literal `/brokers/fyers/exchange-code`, and
   a route that answers `400 No Fyers credentials found` — present, reachable, correct — was listed
   as "not in spec".

So these tests pin properties, not outputs. The tool's output changes as the app changes; the rules
it applies must not.
"""

import importlib.util
import pathlib
import sys

import pytest

TOOL = pathlib.Path(__file__).resolve().parents[2] / "web" / "scripts" / "audit_api_contracts.py"
API_TS = pathlib.Path(__file__).resolve().parents[2] / "web" / "lib" / "api.ts"


def load_tool():
    spec = importlib.util.spec_from_file_location("audit_api_contracts", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tool = load_tool()


class TestMethodComesFromTheCallsOwnArguments:
    def test_a_neighbouring_method_is_not_borrowed(self):
        """The exact shape that produced twelve false WRONG-METHOD findings."""
        src = """
          readOne:  () => request('/engine/orders'),
          cancel:   (id: string) => request(`/engine/orders/${id}/cancel`, { method: 'POST' }),
        """
        found = tool.find_untyped_declarations(src)
        by_path = {p: m for _d, p, _o, m in found}
        assert by_path["/engine/orders"] is None, "a read must not inherit the next call's POST"
        assert by_path is not None

    def test_a_method_on_the_same_call_is_read(self):
        src = "send: (d: object) => request('/brokers/fyers/exchange-code', { method: 'POST', body: d })"
        found = tool.find_untyped_declarations(src)
        assert found and found[0][3] == "POST"

    def test_a_multiline_argument_list_is_still_read(self):
        src = """
          x: () => request('/a/b', {
            method: 'DELETE',
          })
        """
        assert tool.find_untyped_declarations(src)[0][3] == "DELETE"

    def test_a_method_far_down_the_file_is_not_reached(self):
        src = "a: () => request('/one')\n" + "\n" * 60 + "b: () => request('/two', { method: 'POST' })"
        by_path = {p: m for _d, p, _o, m in tool.find_untyped_declarations(src)}
        assert by_path["/one"] is None
        assert by_path["/two"] == "POST"


class TestPathsMatchByShapeNotByString:
    ROUTES = {
        "/brokers/*/exchange-code": {"POST"},
        "/forward-tests/*": {"GET"},
        "/admin/brokers/fyers/re-auth/*": {"POST"},
    }

    def test_a_literal_segment_matches_a_parameter_in_the_spec(self):
        index = tool.spec_index(self.ROUTES)
        assert tool.methods_for("/brokers/fyers/exchange-code", index) == {"POST"}

    def test_a_fixed_literal_in_the_spec_still_has_to_agree(self):
        """Shape matching must not turn two different endpoints into one."""
        index = tool.spec_index(self.ROUTES)
        assert tool.methods_for("/brokers/kotak/exchange-code", index) == {"POST"}
        assert tool.methods_for("/admin/brokers/zerodha/re-auth/7", index) is None

    def test_a_shorter_or_longer_path_does_not_match(self):
        index = tool.spec_index(self.ROUTES)
        assert tool.methods_for("/brokers/fyers", index) is None
        assert tool.methods_for("/brokers/fyers/exchange-code/extra", index) is None

    def test_a_genuinely_unknown_path_is_still_unknown(self):
        index = tool.spec_index(self.ROUTES)
        assert tool.methods_for("/admin/pnl", index) is None

    def test_check_methods_actually_routes_through_the_shape_helpers(self):
        """Pins the wiring, not just the helpers.

        Testing `methods_for` directly was not enough: a version of `check_methods` that looks paths
        up with `routes.get(path)` passes every helper test in this class while silently reverting to
        the exact-string behaviour, which is the bug. This goes through `check_methods` so that
        reversion is visible.
        """
        spec = {"/brokers/*/exchange-code": {"GET"}}
        declarations = {
            ("POST", "/brokers/fyers/exchange-code"): [(TOOL, 1, None, "POST")],
        }
        problems = tool.check_methods(declarations, spec)
        assert [p[0] for p in problems] == ["WRONG-METHOD"], (
            "a literal client path must still be checked against a parameterised spec path"
        )
        assert problems[0][1] == "/brokers/fyers/exchange-code"
        assert problems[0][3] == "GET"

    def test_check_methods_reports_a_post_only_path_reached_with_the_default_verb(self):
        spec = {"/risk/live/disable": {"POST"}}
        declarations = {
            ("?", "/risk/live/disable"): [(TOOL, 507, None, None)],
        }
        problems = tool.check_methods(declarations, spec)
        assert [p[0] for p in problems] == ["NO-METHOD"]
        assert problems[0][2] == "GET (default)"
        assert problems[0][3] == "POST"


class TestUntypedDeclarationsAreFoundAtAll:
    def test_an_untyped_call_is_visible(self):
        """The blind spot that hid `disableLive`: the typed scanner only matches `request<`."""
        found = tool.find_untyped_declarations("x: () => request('/risk/live/disable')")
        assert len(found) == 1 and found[0][1] == "/risk/live/disable"

    def test_a_typed_call_is_left_to_the_typed_scanner(self):
        assert tool.find_untyped_declarations("x: () => request<Foo>('/a')") == []

    def test_an_interpolated_path_is_skipped_rather_than_guessed(self):
        assert tool.find_untyped_declarations("x: () => request(`/a/${id}`)") == []

    def test_a_call_with_no_literal_path_is_skipped(self):
        assert tool.find_untyped_declarations("x: () => request(buildPath())") == []


class TestDisableLiveRegression:
    """The bug this whole exercise came from.

    `disableLive` declared no method, so it defaulted to GET, while the API offers POST only. The
    result is 405 on first use — and because no page calls it, nothing in the app ever notices.
    Verified live: GET returns 405, POST returns 200 "LIVE trading disabled".
    """

    def test_it_declares_post(self):
        source = API_TS.read_text()
        assert "request('/risk/live/disable')" not in source, (
            "disableLive is calling a POST-only endpoint with the default GET"
        )
        assert "request('/risk/live/disable', { method: 'POST' })" in source

    def test_the_spec_only_offers_post(self):
        """Why GET cannot work, stated as a fact about the API rather than a belief."""
        handlers = pathlib.Path(__file__).resolve().parents[1] / "routes" / "v1_risk.py"
        source = handlers.read_text()
        assert '@router.post("/live/disable")' in source
        assert '@router.get("/live/disable")' not in source


class TestNoClientDeclarationDefaultsToGetOnAMutatingName:
    """A self-contained invariant that would have caught this without a spec fixture.

    Any client method whose name is a state-changing verb must name its HTTP method. The rule is
    anchored rather than a prefix search, because a prefix search flags reads: `trades` begins with
    `trade` and is a plain GET of `/paper/trades`. A name qualifies only when it is exactly the verb,
    or the verb followed by an uppercase letter — so `disableLive` and `addOrderNote` qualify while
    `trades` does not.
    """

    MUTATING = ("disable", "enable", "delete", "remove", "cancel", "create", "add",
                "update", "place", "deploy", "start", "stop", "pause", "resume",
                "toggle", "rollback", "archive", "submit", "send", "signout",
                "reconcile", "restart", "clone", "publish", "compile", "trade")

    @staticmethod
    def _is_mutating_name(name: str) -> bool:
        for verb in TestNoClientDeclarationDefaultsToGetOnAMutatingName.MUTATING:
            if name == verb:
                return True
            if name.startswith(verb) and name[len(verb):][:1].isupper():
                return True
        return False

    def test_reads_named_after_a_verb_are_not_flagged(self):
        """`trades` starts with `trade` and is a GET. This is why the rule is anchored."""
        assert not self._is_mutating_name("trades")
        assert not self._is_mutating_name("tradesList")
        assert self._is_mutating_name("trade")
        assert self._is_mutating_name("tradeNow")

    @pytest.mark.parametrize("name,expected", [
        ("disableLive", True), ("enableKillSwitch", True), ("addOrderNote", True),
        ("deleteCredentials", True), ("disable", True),
        ("trades", False), ("orders", False), ("listStrategies", False),
        ("updatedAt", False), ("createSomething", True),
    ])
    def test_the_verb_rule_is_exact(self, name, expected):
        assert self._is_mutating_name(name) is expected

    def test_no_mutating_declaration_is_left_to_the_default_verb(self):
        source = API_TS.read_text()
        offenders = []
        for line in source.splitlines():
            stripped = line.strip()
            if "request" not in stripped or "method:" in stripped:
                continue
            name = stripped.split(":", 1)[0].strip()
            if self._is_mutating_name(name):
                offenders.append(stripped[:90])
        assert not offenders, "these mutating declarations send no explicit method:\n" + "\n".join(offenders)