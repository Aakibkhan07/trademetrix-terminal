"""Regression tests for the duplicate Dhan websocket implementation.

`brokers/dhan_adapter.py` used to carry a second, independent Dhan websocket client
alongside the verified `market/dhan_feed.py`. It was reachable -- `market/data_socket.py`
calls `adapter.stream(...)` when it starts a broker feed -- and it could never have
worked. These tests pin the properties that make it impossible to reintroduce.

Every source-level assertion here tokenizes or parses the file first. A plain substring
search over this module would match the docstring that *describes* the old bug and would
report the defect while it was fixed -- or, worse, pass on a file that only described it.
That is not hypothetical: this project's own history has three audit tools that fabricated
findings for exactly this reason.
"""
from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path

import pytest

from brokers.dhan_adapter import DhanAdapter

ADAPTER = Path("brokers/dhan_adapter.py")
FEED = Path("market/dhan_feed.py")
DATA_SOCKET = Path("market/data_socket.py")


def executable_source(path: Path) -> str:
    """Source with comments and string literals removed.

    Tokenizing, then re-emitting, leaves only names, operators and literals-as-code. The
    defect markers this suite hunts for all appear in explanatory prose in this file, so a
    check that reads raw text cannot distinguish "uses client.stream()" from "explains why
    client.stream() does not work".
    """
    out = []
    for tok in tokenize.generate_tokens(io.StringIO(path.read_text()).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        out.append(tok.string)
    return " ".join(out)


def code_with_literals(path: Path) -> str:
    """Source with comments and docstrings removed but *string literals kept*.

    `executable_source` strips every string, which is what makes it reliable for
    code-shape defects -- and completely blind to defects whose value *is* a string: a wrong
    feed host, a wrong JSON field name, ``RequestCode: 1``. The mutation check proved this
    rather than assuming it: reintroducing ``self._ws_url = "wss://api.dhan.co/v2/ws"``
    survived every test, because the only assertion looking for it read text from which all
    strings had already been removed.

    So there are two views, and both are needed:
      * `executable_source` -- no strings. For "does this call the wrong function".
      * this one -- strings kept. For "is the wrong value being sent".
    """
    tree = ast.parse(path.read_text())
    docstrings = docstring_nodes(tree)
    keep = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }
    out = []
    for tok in tokenize.generate_tokens(io.StringIO(path.read_text()).readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING and tok.string not in {repr(s) for s in keep}:
            # A docstring, or f-string scaffolding: not a value being sent.
            continue
        out.append(tok.string)
    return " ".join(out)


def docstring_nodes(tree: ast.Module) -> set[int]:
    """ids() of every docstring constant in the tree.

    A docstring is an `ast.Expr` whose value is a bare string -- module, class and function
    alike. Collecting them from a *single* parse matters: comparing node identity across two
    separate `ast.parse` calls of the same text always fails, because each parse allocates
    new nodes. That mistake made the first version of this helper report the module
    docstring as a code string, which is what put a false failure in front of me.
    """
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                if isinstance(body[0].value.value, str):
                    found.add(id(body[0].value))
    return found


def code_strings(path: Path) -> list[str]:
    """Every string constant that is real code, excluding every docstring."""
    tree = ast.parse(path.read_text())
    docstrings = docstring_nodes(tree)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


# ── 1. the old connection mechanism ─────────────────────────────────────────


class TestNoHttpxStreamForWebsocket:
    def test_the_adapter_never_calls_client_stream(self):
        """httpx cannot upgrade to a websocket. This was the original defect."""
        code = executable_source(ADAPTER)
        assert "client.stream(" not in code, (
            "brokers/dhan_adapter.py calls client.stream(); httpx has no websocket "
            "upgrade, so the connection could never become a websocket"
        )

    def test_the_adapter_does_not_open_a_websocket_itself(self):
        """Exactly one place may open a Dhan socket: market/dhan_feed.py."""
        assert "websockets.connect" not in executable_source(ADAPTER), (
            "the adapter opened its own websocket; there must be one Dhan feed "
            "implementation and it is market/dhan_feed.py"
        )

    def test_only_the_feed_module_declares_the_dhan_feed_host(self):
        """The feed host must not be spelled out a second time.

        Asserted against `code_strings`, not raw text: `market/dhan_feed.py` also names the
        host in its module docstring, and a raw-text check could be satisfied by prose.
        """
        assert not [s for s in code_strings(ADAPTER) if "api-feed" in s], (
            "the adapter names Dhan's feed host itself; it must come from "
            "market.dhan_feed.DHAN_FEED_WSS_URL"
        )
        assert "wss://api-feed.dhan.co" in code_strings(FEED), (
            "market/dhan_feed.py must declare DHAN_FEED_WSS_URL as the single feed endpoint"
        )

    def test_the_wrong_feed_host_is_not_used_as_a_url_anywhere(self):
        """`wss://api.dhan.co/v2/ws` was wrong in both host and path.

        Read through `code_with_literals`, not `executable_source`. A comment or a docstring
        is allowed to name the old URL -- explaining why it was wrong is the point -- but a
        live string constant is not.
        """
        for path in (ADAPTER, FEED, DATA_SOCKET):
            literals = code_strings(path)
            for value in literals:
                assert "wss://api.dhan.co" not in value, (
                    f"{path} holds the wrong Dhan feed host as a live string: {value!r}"
                )
                assert "api.dhan.co/v2/ws" not in value, (
                    f"{path} holds the wrong Dhan feed path as a live string: {value!r}"
                )


# ── 2. the old subscription payload ──────────────────────────────────────────


class TestNoOldProtocolInSubscription:
    def test_request_code_1_is_not_a_subscription_code(self):
        """v2 subscribes with 15/17/21. RequestCode 1 was never valid for v2."""
        assert '"RequestCode": 1' not in code_with_literals(ADAPTER)
        assert "'RequestCode': 1" not in code_with_literals(ADAPTER)

    def test_the_adapter_does_not_build_a_subscribe_frame_itself(self):
        """Frame construction belongs to market/dhan_feed.build_subscribe_frame."""
        assert "RequestCode" not in code_strings(ADAPTER), (
            "the adapter still builds a subscription frame itself; RequestCode must come "
            "from the verified feed implementation"
        )

    def test_security_token_is_never_sent(self):
        """v2 uses SecurityId. `SecurityToken` is not a v2 field."""
        assert "SecurityToken" not in code_strings(ADAPTER)
        assert "SecurityToken" not in executable_source(FEED)

    def test_the_adapter_does_not_default_the_segment_to_nse_eq(self):
        """A derivative subscribed to NSE_EQ is the exact original defect."""
        strings = code_strings(ADAPTER)
        assert "NSE_EQ" not in strings, (
            "NSE_EQ appears as a live string constant in the adapter. It is legitimate "
            "only inside the verified segment-name lookup tables in market/dhan_feed.py, "
            "never as a default in the adapter."
        )

    def test_the_verified_tables_keep_their_documented_segment_names(self):
        """The guard above must not be satisfied by deleting correct lookup data."""
        feed_strings = code_strings(FEED)
        assert "NSE_EQ" in feed_strings, (
            "market/dhan_feed.py should still map Dhan segment code 1 to NSE_EQ; "
            "removing it would break equity subscriptions"
        )

    def test_a_display_symbol_is_never_substituted_for_a_security_id(self):
        """Subscriptions are built from resolved contract metadata only."""
        assert "symbol_for_contract" not in executable_source(ADAPTER)
        source = ADAPTER.read_text()
        assert "subscription_for_instrument" in source, (
            "stream() must build subscriptions from resolved contract metadata"
        )
        # The resolver, not the caller's symbol, is what supplies segment and id.
        assert "instrument_resolver.resolve(" in source


# ── 3. the token is read from the column Dhan actually stores it in ─────────


class TestDhanTokenColumn:
    def test_the_feed_reads_the_dhan_token_from_the_column_that_holds_it(self):
        """Dhan keeps its access token in encrypted_secret_key.

        Reading only encrypted_access_token handed the feed an empty token, authenticate
        raised, and the exception was swallowed into a Yahoo fallback.
        """
        source = DATA_SOCKET.read_text()
        assert 'broker_type == "dhan"' in source, (
            "market/data_socket.py must special-case Dhan's token column"
        )
        assert "raw_token = secret_key" in source, (
            "the Dhan token fallback from encrypted_secret_key is missing"
        )


# ── 4. unresolvable symbols are refused, not defaulted ───────────────────────


class TestUnresolvableSymbolsAreRefused:
    @pytest.mark.asyncio
    async def test_a_symbol_with_no_metadata_opens_no_feed_at_all(self, monkeypatch):
        """Fail closed. An empty subscription set must not produce a feed."""
        a = DhanAdapter()
        a._access_token = "token"
        a._client_id = "1100793385"

        import market.instruments as instruments

        monkeypatch.setattr(
            instruments.instrument_resolver, "resolve", lambda *a, **k: None,
        )
        with pytest.raises(RuntimeError, match="no feed was opened"):
            await a.stream(["NOT-A-REAL-CONTRACT"], lambda t: None)

    @pytest.mark.asyncio
    async def test_an_unresolvable_symbol_is_refused_while_a_good_one_proceeds(
        self, monkeypatch, caplog
    ):
        """One bad symbol must not silently become NSE_EQ, and must not kill the feed."""
        from market.instruments import Instrument

        a = DhanAdapter()
        a._access_token = "token"
        a._client_id = "1100793385"

        good = Instrument(
            broker="dhan", broker_symbol="NIFTY-Oct2026-23250-CE", underlying="NIFTY",
            instrument_type="OPT", exchange_segment="NSE_FNO", security_id="40749",
            lot_size=65, expiry="2026-10-06", strike=23250.0, option_type="CE",
        )

        import market.instruments as instruments

        monkeypatch.setattr(
            instruments.instrument_resolver, "resolve",
            lambda sym, **k: good if sym == "GOOD" else None,
        )

        captured: dict = {}

        class _Feed:
            def __init__(self, token, cid, *, on_event=None, **kw):
                captured["token"] = token
                captured["cid"] = cid
                captured["on_event"] = on_event

            def subscribe(self, subs):
                captured["subs"] = list(subs)

            async def run(self):
                return None

            async def stop(self):
                return None

        monkeypatch.setattr("market.dhan_feed.DhanMarketFeed", _Feed)

        with caplog.at_level("ERROR"):
            await a.stream(["GOOD", "BAD"], lambda t: None)

        subs = captured["subs"]
        assert len(subs) == 1
        # The good subscription carries the resolved segment and numeric id, not the symbol.
        assert subs[0].exchange_segment == "NSE_FNO"
        assert subs[0].security_id == "40749"
        assert "BAD" in caplog.text, "the refused symbol must be named in the log"


# ── 5. delegation, not duplication ──────────────────────────────────────────


class TestStreamDelegatesToTheVerifiedFeed:
    @pytest.mark.asyncio
    async def test_stream_opens_a_market_feed_and_runs_it(self, monkeypatch):
        a = DhanAdapter()
        a._access_token = "token"
        a._client_id = "1100793385"

        from market.instruments import Instrument

        inst = Instrument(
            broker="dhan", broker_symbol="NIFTY-Oct2026-23250-CE", underlying="NIFTY",
            instrument_type="OPT", exchange_segment="NSE_FNO", security_id="40749",
            lot_size=65, expiry="2026-10-06", strike=23250.0, option_type="CE",
        )
        import market.instruments as instruments
        monkeypatch.setattr(instruments.instrument_resolver, "resolve", lambda *a, **k: inst)

        ran = {"n": 0}

        class _Feed:
            def __init__(self, *a, **k):
                pass

            def subscribe(self, subs):
                self.subs = list(subs)

            async def run(self):
                ran["n"] += 1

            async def stop(self):
                return None

        monkeypatch.setattr("market.dhan_feed.DhanMarketFeed", _Feed)
        await a.stream(["NIFTY-Oct2026-23250-CE"], lambda t: None)
        assert ran["n"] == 1, "stream() must run the verified feed, not its own loop"

    @pytest.mark.asyncio
    async def test_a_packet_without_a_price_is_not_published_as_a_tick(self, monkeypatch):
        """A zero last_price reads downstream as a real quote."""
        import asyncio as _asyncio

        a = DhanAdapter()
        a._access_token = "token"
        a._client_id = "1100793385"

        from market.instruments import Instrument

        inst = Instrument(
            broker="dhan", broker_symbol="X", underlying="NIFTY", instrument_type="OPT",
            exchange_segment="NSE_FNO", security_id="40749", lot_size=65,
            expiry="2026-10-06", strike=23250.0, option_type="CE",
        )
        import market.instruments as instruments
        monkeypatch.setattr(instruments.instrument_resolver, "resolve", lambda *a, **k: inst)

        holder = {}

        class _Feed:
            def __init__(self, *a, on_event=None, **k):
                holder["on_event"] = on_event

            def subscribe(self, subs):
                pass

            async def run(self):
                from market.dhan_feed import DhanMarketEvent
                emit = holder["on_event"]
                # An open-interest-only packet: real, but carries no price.
                from datetime import UTC, datetime
                await emit(DhanMarketEvent(
                    packet_type="oi", exchange_segment="NSE_FNO", security_id="40749",
                    provider="dhan", timestamp=datetime.now(UTC),
                    ltp=None, open_interest=100,
                ))
                return None

            async def stop(self):
                return None

        monkeypatch.setattr("market.dhan_feed.DhanMarketFeed", _Feed)
        ticks = []
        await a.stream(["X"], ticks.append)
        assert ticks == [], f"a packet with no price must not become a tick, got {ticks}"
