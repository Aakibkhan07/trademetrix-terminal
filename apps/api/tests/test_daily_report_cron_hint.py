"""The documented cron command has to be a command that works.

`POST /reports/daily/send` is guarded by `X-Cron-Secret` and the hint that tells an operator how to
schedule it was wrong in three ways at once:

    curl -s http://127.0.0.1:8000/api/v1/reports/daily/send -H X-Cron-Secret:$CRON_SECRET

`curl` defaults to GET, the endpoint is `@router.post`, so the documented command answered 405 and
the daily report never arrived — silently, into a cron log nobody reads. It also pointed at a port
production compose never publishes, and the two copies of it (this message and the one rendered on
`/reports/daily`) disagreed about quoting.

Both are built from the base URL in play now, so neither can name a host that does not serve. These
tests assert the properties that would catch a regression, and they read the frontend source too
because a hint that only the API fixes is still a hint a user can copy and get wrong.
"""

import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CRON_RE = re.compile(r"curl -s -X POST (\S+) -H \"X-Cron-Secret: \$CRON_SECRET\"")
LOCALHOST_RE = re.compile(r"curl[^\n]*?(127\.0\.0\.1|localhost):")


class TestDailyReportCronHint:
    @pytest.fixture()
    def client(self, monkeypatch):
        monkeypatch.setenv("CRON_SECRET", "test-cron-secret")
        from fastapi.testclient import TestClient

        from main import app

        return TestClient(app)

    def _hint(self, client) -> str:
        r = client.post("/api/v1/reports/daily/send", headers={"X-Cron-Secret": "test-cron-secret"})
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:200]}"
        return r.json()["message"]

    def test_hint_uses_post(self, client):
        """The bug: a GET against a POST endpoint answers 405 and delivers nothing."""
        hint = self._hint(client)
        assert "-X POST" in hint, f"the documented curl does not use POST: {hint!r}"

    def test_hint_quotes_the_secret_header(self, client):
        """Unquoted, a secret containing a space silently becomes two arguments."""
        hint = self._hint(client)
        assert '"X-Cron-Secret: $CRON_SECRET"' in hint, f"header is not quoted: {hint!r}"

    def test_hint_does_not_hardcode_a_host(self, client):
        """`127.0.0.1:8000` answers nowhere on the VPS — compose does not publish that port."""
        hint = self._hint(client)
        assert not LOCALHOST_RE.search(hint), f"hint names a host that will not serve it: {hint!r}"

    def test_hint_matches_this_server(self, client):
        """Derived from the request, so it is right for whatever host is actually answering."""
        hint = self._hint(client)
        m = CRON_RE.search(hint)
        assert m, f"could not parse a complete cron command out of: {hint!r}"
        url = m.group(1)
        assert url.endswith("/api/v1/reports/daily/send"), url
        # The endpoint this hint points at must accept the method the hint names. Keep the path the
        # hint gave rather than reconstructing it — reconstructing it is what the hint got wrong.
        target = "/" + url.split("://", 1)[1].split("/", 1)[1]
        r = client.post(target, headers={"X-Cron-Secret": "test-cron-secret"})
        assert r.status_code == 200, (
            f"hint names {url} -> {target}, which answered {r.status_code}; a cron following it "
            f"would get {r.status_code}, not a report"
        )

    def test_frontend_hint_matches_the_same_properties(self):
        """The copy a user actually reads is rendered on the page, not this message.

        Fixing only the API would leave a command on screen that still 405s, so the page source is
        checked for the same three properties.
        """
        page = ROOT.parent / "web" / "app" / "reports" / "daily" / "page.tsx"
        if not page.exists():
            pytest.skip("web app not present")
        source = page.read_text()
        # strip comments so the historical explanation cannot satisfy the assertion
        code = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
        code = re.sub(r"//[^\n]*$", "", code, flags=re.M)

        assert "-X POST" in code, "the page's cron hint does not use POST"
        assert "127.0.0.1:8000" not in code, "the page's cron hint still hardcodes localhost"
        assert "API_BASE" in code, (
            "the page's cron hint must derive its URL from API_BASE, the value it already uses for "
            "every other request, so the hint cannot disagree with where the page's data comes from"
        )
        assert "curl -s -X POST {cronUrl}" in code, (
            "the page should interpolate cronUrl; a literal URL in JSX would be a hardcoded host"
        )
