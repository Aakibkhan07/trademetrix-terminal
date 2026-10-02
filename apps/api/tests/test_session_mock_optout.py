"""The escape hatch has to actually restore the real behaviour.

`without_session_mocks()` exists because three tests were silently broken by the
session-scoped patches in `conftest.py` (see the note there). A helper that looks
right and does not restore anything would simply be a fourth.

So this asserts the *effect*, not the mechanism: inside the context the real
`increment` runs and counts; outside it, the stub does. If someone changed the
helper to re-patch nothing, or patched the wrong module, these fail.
"""
import pytest

from core.cache import cache
from tests.conftest import _apply_test_mocks, without_session_mocks


@pytest.fixture(autouse=True)
def _mocks_are_applied():
    """Force the session mocks on before each test here.

    `_apply_test_mocks` is lazy — it runs on the first use of the `client` fixture, not at
    session start. A test file that never uses `client` therefore runs with the *real*
    implementations, so asserting "the stub is back" without this would pass vacuously
    against code that had never mocked anything.

    Worth stating because it is the same trap as the leak itself in miniature: what you
    observe depends on ordering, and nothing tells you.
    """
    _apply_test_mocks()


@pytest.mark.asyncio
async def test_the_real_increment_is_available_inside_the_context():
    class FakeRedis:
        # `ttl_value`, not `ttl`: an attribute named `ttl` would shadow the method the
        # cache calls, and the TypeError is swallowed by the cache's own `except`, which
        # returns 0 and makes the test fail on an arithmetic assertion instead of on the
        # real cause. `test_cache_counter_ttl.py` already had this right.
        def __init__(self):
            self.value = 5
            self.ttl_value = 42
            self.expire_calls = []

        async def incr(self, key):
            self.value += 1
            return self.value

        async def ttl(self, key):
            return self.ttl_value

        async def expire(self, key, ttl):
            self.expire_calls.append((key, ttl))
            self.ttl_value = ttl
            return True

    fake = FakeRedis()
    cache._redis = fake
    cache._enabled = True
    try:
        with without_session_mocks():
            # The real method: 5 -> 6, and a healthy TTL is left alone.
            assert await cache.increment("ratelimit:1.2.3.4", ttl=60) == 6
            assert fake.expire_calls == []
    finally:
        cache._enabled = False


@pytest.mark.asyncio
async def test_the_stub_is_back_after_the_context_exits():
    """Restoring has to be symmetric, or every later test in the session is affected."""
    with without_session_mocks():
        pass
    # The conftest stub returns a constant 1 regardless of the key.
    assert await cache.increment("anything") == 1


@pytest.mark.asyncio
async def test_a_failure_inside_the_context_still_restores():
    """A test that raises must not leave the whole session unpatched.

    This is the case that turns one broken test into fifty: without the `finally`, the
    exception propagates, the mocks stay stopped, and every subsequent test sees real
    behaviour while the rest of the suite expects the stub.
    """
    with pytest.raises(RuntimeError):
        with without_session_mocks():
            raise RuntimeError("boom")

    assert await cache.increment("anything") == 1
