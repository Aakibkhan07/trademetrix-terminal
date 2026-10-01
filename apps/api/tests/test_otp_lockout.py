"""The OTP verify lockout: a brute-force control, with no prior test.

`POST /api/v1/auth/verify-otp` guards a **6-digit** code. The whole reason 6 digits is
survivable is the lockout behind it: `_OTP_MAX_VERIFY_ATTEMPTS = 5` failures sets a
5-minute block (`routes/v1_auth.py`). Without it, a 6-digit space is 10^6 and an
attacker who can send requests gets a real brute-force surface.

That control had **no test at all**. `tests/test_auth_throttle.py` covers
`_throttle_login`, which is a different function using `cache.get`/`cache.set`, and
installs its own counter with `monkeypatch`. Nothing exercised
`_check_otp_verify_lockout` or `_record_otp_verify_attempt`.

Why it was never trivial to add, and the trap in writing one
-------------------------------------------------------------
`increment` is the hinge of the whole control:

    count = await cache.increment(_otp_redis_key_attempts(email), ttl=...)
    if count >= _OTP_MAX_VERIFY_ATTEMPTS:   # 5
        await cache.set(_otp_redis_key_lockout(email), ...)

A test that reaches for the ambient `core.cache.cache` singleton cannot exercise this,
and it fails in a way that misdirects the investigation. Measured, both ways round:

* **isolated** (`pytest tests/test_otp_lockout.py`) — there is no Redis in the test
  environment, so `RedisCache._enabled` is False and `increment` returns **0**.
* **as CI runs it** (`pytest tests/`, after any `client`-fixture test) — conftest has
  replaced `increment` with a stub returning a constant **1**.

Either way `count` never reaches 5, the lockout branch never runs, and
`_check_otp_verify_lockout` reads `cache.get` — which is *also* stubbed in CI, and reads a
store unrelated to the increment stub's. The test then fails at "the lockout did not
engage", which reads as a bug in `_record_otp_verify_attempt`. The `>=` is correct; the
count simply never gets there. That is the same shape as `test_cache_counter_ttl.py`,
where the failures named the TTL logic rather than the harness — except there the
production bug was real and here it is not, so the same red output points at the wrong
file entirely.

Verified rather than assumed: a naive version of this test (`/tmp/naive_test.py`, five
calls to the real `_record_otp_verify_attempt`, asserting the lockout) fails under **both**
invocations. An earlier draft of this docstring claimed it would *pass* vacuously. That
was wrong, and the experiment is what showed it — the accurate claim is the one above.

So every test here installs its own counter with `monkeypatch.setattr` on
`routes.v1_auth.cache`, the style `test_auth_throttle.py` already uses. None rely on the
singleton's state, and this file's ordering relative to the `client` fixture does not
matter — both invocations give the same 7 passes.

What is asserted is the *behaviour*, not the wiring: five wrong codes are refused, the
sixth is refused by the lockout rather than by the comparison, and a correct code after
the lockout still cannot get in. The last one is the one that matters — it distinguishes
"the lockout engaged" from "the code happened to be wrong". Both mutations confirm these
are load-bearing: `>=` → `>` fails 3, and disabling the branch entirely fails 4.
"""

import pytest
from fastapi import HTTPException

from routes import v1_auth
from routes.v1_auth import (
    _OTP_MAX_VERIFY_ATTEMPTS,
    _OTP_VERIFY_LOCKOUT,
    _check_otp_verify_lockout,
    _clear_otp,
    _record_otp_verify_attempt,
    _store_otp_code,
)


@pytest.fixture
def otp_cache(monkeypatch):
    """An in-memory stand-in for the four cache calls this control makes.

    Deliberately not the singleton. `conftest` stubs `increment` to a constant 1, which
    is below `_OTP_MAX_VERIFY_ATTEMPTS`, so against the real singleton these tests would
    pass without the lockout ever engaging. See the module docstring.
    """
    store: dict[str, object] = {}
    calls: dict[str, int] = {"increment": 0, "set": 0, "delete": 0, "get": 0}

    async def fake_get(key, default=None):
        calls["get"] += 1
        return store.get(key, default)

    async def fake_set(key, value, ttl=None, *a, **k):
        calls["set"] += 1
        store[key] = value
        return True

    async def fake_delete(key, *a, **k):
        calls["delete"] += 1
        store.pop(key, None)
        return True

    async def fake_increment(key, ttl=None, *a, **k):
        # The real semantic: INCR then, on first write, set the expiry. `increment` in
        # core/cache.py also re-arms a TTL the key has lost, which these tests do not
        # need to model — they are about the threshold, not the expiry.
        calls["increment"] += 1
        current = int(store.get(key, 0)) + 1
        store[key] = current
        return current

    monkeypatch.setattr(v1_auth.cache, "get", fake_get)
    monkeypatch.setattr(v1_auth.cache, "set", fake_set)
    monkeypatch.setattr(v1_auth.cache, "delete", fake_delete)
    monkeypatch.setattr(v1_auth.cache, "increment", fake_increment)
    return {"store": store, "calls": calls}


@pytest.mark.asyncio
async def test_one_wrong_attempt_does_not_lock_out(otp_cache):
    await _record_otp_verify_attempt("a@b.com", valid=False)
    allowed, err = await _check_otp_verify_lockout("a@b.com")
    assert allowed is True, err


@pytest.mark.asyncio
async def test_the_lockout_engages_exactly_at_the_threshold(otp_cache):
    """Below the threshold: allowed. At it: refused.

    `>` vs `>=` is the whole question — an off-by-one here either locks a legitimate
    user out one attempt early, or lets the extra attempt through.
    """
    for _ in range(_OTP_MAX_VERIFY_ATTEMPTS - 1):
        await _record_otp_verify_attempt("a@b.com", valid=False)
        allowed, _ = await _check_otp_verify_lockout("a@b.com")
        assert allowed is True, "locked out before reaching the configured threshold"

    await _record_otp_verify_attempt("a@b.com", valid=False)
    allowed, err = await _check_otp_verify_lockout("a@b.com")
    assert allowed is False, "the lockout did not engage at the threshold"
    assert err and "Too many failed attempts" in err


@pytest.mark.asyncio
async def test_the_lockout_records_a_remaining_time(otp_cache):
    await _record_otp_verify_attempt("a@b.com", valid=False)
    for _ in range(_OTP_MAX_VERIFY_ATTEMPTS):
        await _record_otp_verify_attempt("a@b.com", valid=False)
    _, err = await _check_otp_verify_lockout("a@b.com")
    # The message names the wait, so the user is told when to retry rather than just
    # being refused. A bare "too many attempts" with no time is the usual version of this
    # bug and it is the one that produces support tickets.
    assert str(_OTP_VERIFY_LOCKOUT) in err, err


@pytest.mark.asyncio
async def test_a_correct_code_does_not_lock_out_and_clears_the_attempts(otp_cache):
    """A successful verify must reset the counter, or the limit is per-lifetime."""
    for _ in range(_OTP_MAX_VERIFY_ATTEMPTS - 1):
        await _record_otp_verify_attempt("a@b.com", valid=False)
    await _record_otp_verify_attempt("a@b.com", valid=True)
    allowed, err = await _check_otp_verify_lockout("a@b.com")
    assert allowed is True, err

    # And the counter is genuinely cleared, not merely unlocked.
    await _record_otp_verify_attempt("a@b.com", valid=False)
    allowed, _ = await _check_otp_verify_lockout("a@b.com")
    assert allowed is True, "the attempt counter was not cleared by a success"


@pytest.mark.asyncio
async def test_lockout_is_per_email(otp_cache):
    """One attacker must not be able to lock a victim's email out.

    The key is derived from the email, so this holds — and it is worth asserting rather
    than assuming, because a key that accidentally omitted the email would make a
    denial-of-service out of the brute-force control.
    """
    for _ in range(_OTP_MAX_VERIFY_ATTEMPTS):
        await _record_otp_verify_attempt("victim@example.com", valid=False)

    blocked, _ = await _check_otp_verify_lockout("victim@example.com")
    assert blocked is False

    allowed, err = await _check_otp_verify_lockout("someone.else@example.com")
    assert allowed is True, "locking one email blocked a different one"


@pytest.mark.asyncio
async def test_a_correct_code_cannot_get_in_during_the_lockout(otp_cache):
    """The lockout is checked before the code is compared.

    This is the assertion that separates "the lockout engaged" from "that code was
    wrong". Without it, a test that stores the right code and submits the wrong one
    proves nothing about the lockout at all.
    """
    await _store_otp_code("a@b.com", "123456")
    for _ in range(_OTP_MAX_VERIFY_ATTEMPTS):
        await _record_otp_verify_attempt("a@b.com", valid=False)

    req = v1_auth.VerifyOTPRequest(email="a@b.com", otp="123456")
    with pytest.raises(HTTPException) as exc:
        await v1_auth.verify_otp(req, _request())
    assert exc.value.status_code == 429, (
        f"expected the lockout to refuse a correct code with 429, got {exc.value.status_code}"
    )


@pytest.mark.asyncio
async def test_successful_verify_clears_the_stored_code_so_it_cannot_be_reused(otp_cache):
    """The OTP is single-use.

    Without the clear, a code that was valid once stays valid for its whole TTL, and an
    attacker who observes one success — or reads a shoulder-surfed code — can replay it
    until it expires.
    """
    await _store_otp_code("a@b.com", "123456")
    await _record_otp_verify_attempt("a@b.com", valid=True)
    await _clear_otp("a@b.com")
    assert await v1_auth._get_stored_otp("a@b.com") is None, (
        "the OTP survived a successful verify and can be replayed until it expires"
    )


def _request():
    """A request object with the attributes `verify_otp` touches before the lockout."""
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/verify-otp",
        "headers": [(b"x-forwarded-for", b"203.0.113.7")],
        "client": ("203.0.113.7", 1234),
        "query_string": b"",
    }
    return Request(scope)
