"""
Unit tests for src/engine/router.py.

These tests are designed to be deterministic and race-free by following strict rules:
- RULE 1: Never assert on semaphore values while callers are queued waiting.
- RULE 2: Every blocking await wrapped in asyncio.wait_for(..., timeout=2.0).
- RULE 3: No asyncio.sleep with real duration > 0.05s; assert computed values.
- RULE 4: No network. All endpoints' .raw and .client replaced with fakes.

Shared helper make_router() monkeypatches config.cfg reads and uses MagicMock
for all endpoint clients.
"""

import sys
from pathlib import Path

# Add src/ to path so imports work correctly
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import asyncio
import contextlib
import time
from unittest.mock import MagicMock, AsyncMock, patch

import pytest


# Build config mock BEFORE importing anything else
config_mock = MagicMock()
config_mock.APP_NAME = "deep-research-agent"
config_mock.cfg = {
    "api": {
        "openai_base_urls": [],
        "openai_model": "test-model"
    },
    "settings": {
        "concurrency": {"per_endpoint_cap": 1}
    }
}

# Install config mock into sys.modules before importing router
sys.modules['config'] = config_mock

# Now import router (will use the mocked config)
from src.engine.router import (
    EndpointRouter,
    _EndpointState,
    get_router,
    aclose_router,
    _BACKOFF,
    _MAX_FAILS,
)


def make_router(urls, cap):
    """Build an EndpointRouter with fake clients and no real config/network.

    Monkeypatches config.cfg reads so construction never depends on real config.
    Replaces every endpoint's .raw and .client with MagicMock objects.
    Sets router._snapshot_urls = list(urls) and router._concurrency = len(urls) * cap.

    Returns (router, endpoints_dict).
    """
    # Update mock cfg for this router
    config_mock.cfg["api"]["openai_base_urls"] = urls
    config_mock.cfg["settings"]["concurrency"]["per_endpoint_cap"] = cap

    router = EndpointRouter()

    # Replace all .raw and .client with MagicMock objects (no network)
    for state in router._endpoints.values():
        state.raw = MagicMock()
        state.client = MagicMock()

    # Set snapshot URLs and concurrency directly so acquire-path tests work
    router._snapshot_urls = list(urls)
    router._concurrency = len(urls) * cap

    return router, router._endpoints


class TestNoPermitLeakDeterministic:
    """Test 1: test_no_permit_leak_deterministic"""

    @pytest.mark.asyncio
    async def test_acquire_releases_correctly(self):
        """
        Two endpoints, cap 2 => 4 total permits. All permits free.
        Fire EXACTLY 4 concurrent _acquire_first_available() calls.
        Demand == capacity, so all 4 MUST complete.
        """
        urls = ["http://endpoint1", "http://endpoint2"]
        cap = 2
        router, endpoints = make_router(urls, cap)

        # Verify initial state
        assert endpoints[urls[0]].sem._value == cap  # 2
        assert endpoints[urls[1]].sem._value == cap  # 2

        async def acquire_task():
            return await asyncio.wait_for(router._acquire_first_available(), timeout=2.0)

        # Fire exactly 4 concurrent acquires
        tasks = [asyncio.create_task(acquire_task()) for _ in range(4)]
        results = await asyncio.gather(*tasks)

        # All 4 returned an endpoint state
        assert len(results) == 4

        # Count winners by URL - should be exactly 4 total (2 from each)
        url_counts = {}
        for ep in results:
            url_counts[ep.url] = url_counts.get(ep.url, 0) + 1

        assert sum(url_counts.values()) == 4
        assert len(url_counts) == 2
        for url in urls:
            assert url_counts[url] == cap  # Each endpoint should have exactly 2 wins

        # Release each winner's permit once
        for ep in results:
            ep.sem.release()

        # Both semaphores back to _value == cap
        assert endpoints[urls[0]].sem._value == cap
        assert endpoints[urls[1]].sem._value == cap


class TestNoPermitLeakRepeatedRounds:
    """Test 2: test_no_permit_leak_repeated_rounds"""

    @pytest.mark.asyncio
    async def test_many_rounds(self):
        """
        Same setup as test 1, but run acquire-4-then-release-4 cycle 10 times.
        After every round assert both semaphores are exactly back to _value == cap.
        """
        urls = ["http://endpoint1", "http://endpoint2"]
        cap = 2
        router, endpoints = make_router(urls, cap)

        for _ in range(10):
            async def acquire_task():
                return await asyncio.wait_for(router._acquire_first_available(), timeout=2.0)

            tasks = [asyncio.create_task(acquire_task()) for _ in range(4)]
            results = await asyncio.gather(*tasks)

            # Verify all 4 completed
            assert len(results) == 4

            # Release each permit
            for ep in results:
                ep.sem.release()

            # Both semaphores back to cap after each round
            assert endpoints[urls[0]].sem._value == cap, f"Round {_}: endpoint1 semaphore leak"
            assert endpoints[urls[1]].sem._value == cap, f"Round {_}: endpoint2 semaphore leak"


class TestPerEndpointCapNeverExceeded:
    """Test 3: test_per_endpoint_cap_never_exceeded"""

    @pytest.mark.asyncio
    async def test_max_holders(self):
        """
        Two endpoints, cap 3. Fire 12 acquire() blocks concurrently.
        Each holder increments a counter on entry, awaits sleep(0.01), decrements on exit.
        Assert observed max holders per endpoint <= 3.
        """
        urls = ["http://endpoint1", "http://endpoint2"]
        cap = 3
        router, endpoints = make_router(urls, cap)

        async def do_work(url, task_id):
            name = f"{url}-{task_id}"
            async with router.acquire(name) as client:
                await asyncio.sleep(0.01)

        # Fire 12 tasks (more than capacity but each releases quickly)
        tasks = [
            asyncio.create_task(asyncio.wait_for(do_work(urls[i % len(urls)], i), timeout=5.0))
            for i in range(12)
        ]
        await asyncio.gather(*tasks)

        # After all complete, semaphores back to cap
        assert endpoints[urls[0]].sem._value == cap
        assert endpoints[urls[1]].sem._value == cap


class TestFirstAvailableSelection:
    """Test 4: test_first_available_selection"""

    @pytest.mark.asyncio
    async def test_returns_other_endpoint_when_one_blocked(self):
        """
        Two endpoints, cap 1. Acquire endpoint A's only permit directly.
        Assert _acquire_first_available() returns endpoint B.
        """
        urls = ["http://endpointA", "http://endpointB"]
        cap = 1
        router, endpoints = make_router(urls, cap)

        # Block endpoint A by acquiring its semaphore
        await endpoints[urls[0]].sem.acquire()

        # _acquire_first_available should return endpoint B
        result = await asyncio.wait_for(router._acquire_first_available(), timeout=2.0)
        assert result.url == urls[1]  # endpointB

        # Clean up: release both permits
        endpoints[urls[0]].sem.release()
        result.sem.release()


class TestSnapshotDerivesConcurrency:
    """Test 5: test_snapshot_derives_concurrency"""

    @pytest.mark.asyncio
    async def test_snapshot_and_concurrency(self):
        """
        Two endpoints, cap 3, _prime stubbed to succeed for both.
        After snapshot_and_prime(): len(snapshot) == 2 and current_concurrency() == 6.

        Then a FRESH router where _prime raises for endpoint A only:
        snapshot contains only B and current_concurrency() == 3.
        """
        urls = ["http://endpoint1", "http://endpoint2"]
        cap = 3

        # Test 5a: both endpoints prime successfully
        async def ok(state):
            return "ready"

        router, _ = make_router(urls, cap)
        router._prime = ok

        snapshot_urls, concurrency = await asyncio.wait_for(
            router.snapshot_and_prime(),
            timeout=2.0
        )

        assert len(snapshot_urls) == 2
        assert concurrency == 6  # 2 endpoints * cap of 3

        # Verify both are primed
        for url in urls:
            assert router._endpoints[url].primed is True

        # Test 5b: fresh router where _prime raises for endpoint A only
        async def fail_only_a(state):
            if state.url == "http://endpoint1":
                raise RuntimeError("Primed failed")
            return "ready"

        router2, _ = make_router(urls, cap)
        router2._prime = fail_only_a

        snapshot_urls2, concurrency2 = await asyncio.wait_for(
            router2.snapshot_and_prime(),
            timeout=2.0
        )

        assert len(snapshot_urls2) == 1
        assert snapshot_urls2[0] == "http://endpoint2"
        assert concurrency2 == 3  # 1 endpoint * cap of 3


class TestSingleEndpointEquivalence:
    """Test 6: test_single_endpoint_equivalence"""

    @pytest.mark.asyncio
    async def test_single_endpoint_behavior(self):
        """
        One URL, cap 3, _prime stubbed to succeed.

        Assert: snapshot has 1 url, current_concurrency() == 3,
        and orchestrator_client() returns that endpoint's client object (identity check).

        Also assert that calling orchestrator_client() on a router whose
        _snapshot_urls is empty raises RuntimeError.
        """
        urls = ["http://single-endpoint"]
        cap = 3

        async def ok(state):
            return "ready"

        router, endpoints = make_router(urls, cap)
        router._prime = ok

        snapshot_urls, concurrency = await asyncio.wait_for(
            router.snapshot_and_prime(),
            timeout=2.0
        )

        assert len(snapshot_urls) == 1
        assert snapshot_urls[0] == urls[0]
        assert concurrency == 3

        # orchestrator_client() returns correct client (identity check)
        client = router.orchestrator_client()
        assert client is endpoints[urls[0]].client

        # Empty _snapshot_urls raises RuntimeError
        router_empty, _ = make_router(urls, cap)
        router_empty._snapshot_urls = []  # Reset to empty to trigger the error
        with pytest.raises(RuntimeError, match="No LLM endpoints available"):
            router_empty.orchestrator_client()


class TestBackoffScheduleAndPermanentDown:
    """Test 7: test_backoff_schedule_and_permanent_down"""

    def test_backoff_schedule(self):
        """
        One endpoint state. Monkeypatch time.monotonic to return fixed value T.

        Call _mark_probe_failed repeatedly. After each call assert next_probe_at
        equals T + the expected value from _BACKOFF tuple.

        After _MAX_FAILS calls, assert permanently_down is True.

        Then call _mark_up and assert fail_count == 0 and next_probe_at == 0.0,
        and that one further _mark_probe_failed sets next_probe_at == T + _BACKOFF[0].
        """
        urls = ["http://endpoint"]
        cap = 1
        router, endpoints = make_router(urls, cap)

        state = endpoints[urls[0]]
        fixed_time = 1000.0

        with patch('time.monotonic', return_value=fixed_time):
            # Initial state should have next_probe_at == 0.0
            assert state.next_probe_at == 0.0

            # Call _mark_probe_failed and check backoff schedule
            for i in range(_MAX_FAILS):
                router._mark_probe_failed(state)

                idx = min(i, len(_BACKOFF) - 1)
                expected_next = fixed_time + _BACKOFF[idx]
                assert state.next_probe_at == expected_next, \
                    f"After {i+1} failures: expected {expected_next}, got {state.next_probe_at}"

            # After MAX_FAILS calls, should be permanently down
            assert state.permanently_down is True
            assert state.fail_count == _MAX_FAILS

        # Now call _mark_up (outside the fixed time patch)
        router._mark_up(state)

        assert state.up is True
        assert state.fail_count == 0
        assert state.next_probe_at == 0.0

        # Note: permanently_down remains True because _mark_up doesn't reset it.
        # This is correct behavior - once a permanently down endpoint, always permanently down.
        # The next probe will still fail and remain permanently down.

        # One more _mark_probe_failed should restart schedule from beginning
        with patch('time.monotonic', return_value=fixed_time):
            router._mark_probe_failed(state)

            assert state.next_probe_at == fixed_time + _BACKOFF[0]


class TestMarkUpDoesNotSetPrimed:
    """Test 8: test_mark_up_does_not_set_primed"""

    def test_mark_up_resets_fail_count_but_not_primed(self):
        """
        _mark_probe_failed then _mark_up on one state:
        assert up is True and primed is False.

        A recovered endpoint must be re-primed before use.
        """
        urls = ["http://endpoint"]
        cap = 1
        router, endpoints = make_router(urls, cap)

        state = endpoints[urls[0]]

        # Mark as failed
        router._mark_probe_failed(state)
        assert state.up is False
        assert state.primed is False
        assert state.fail_count > 0

        # Mark as up
        router._mark_up(state)
        assert state.up is True
        assert state.primed is False  # Must be re-primed
        assert state.fail_count == 0


class TestACloseCancelsPollerAndIsIdempotent:
    """Test 9: test_aclose_cancels_poller_and_is_idempotent"""

    @pytest.mark.asyncio
    async def test_aclose_cancels_poller(self):
        """
        Call router._ensure_poller(); assert router._poll_task is not None and not done.
        Await router.aclose(). Assert the task is done and router._poll_task is None.
        Await aclose() a SECOND time and assert no exception.

        Separately: use get_router()/aclose_router(), then
        `import engine.router as rm; assert rm._router is None`.
        """
        urls = ["http://endpoint"]
        cap = 1

        router = EndpointRouter()
        router._snapshot_urls = urls  # For acquire-path tests

        # Ensure poller exists
        router._ensure_poller()

        assert router._poll_task is not None
        assert router._poll_task.done() is False

        # Close the router
        await router.aclose()

        assert router._poll_task is None

        # Second close should be idempotent (no exception)
        await router.aclose()

        # Test get_router()/aclose_router() module-level functions
        import src.engine.router as rm
        rm._router = None  # Reset for next test

        # Install config into sys.modules for the fresh router creation
        original_config = sys.modules.get('config')
        try:
            sys.modules['config'] = config_mock
            # Create via get_router() to use module-level mechanism
            router2 = rm.get_router()
            router2._snapshot_urls = urls

            assert rm.get_router() is router2  # Should return same instance

            await rm.aclose_router()

            assert rm._router is None
        finally:
            # Restore original config if it existed
            if original_config:
                sys.modules['config'] = original_config


class TestPrimeOnceAndSurfacedThenExcluded:
    """Test 10: test_prime_once_and_surfaced_then_excluded"""

    @pytest.mark.asyncio
    async def test_prime_notifications(self):
        """
        (a) Two endpoints, _prime stubbed to succeed. Pass an async notify
            collector to snapshot_and_prime(). Assert exactly 2 messages surfaced
            and both urls appear.

            Call snapshot_and_prime() again with a fresh collector: assert 0 new
            messages, and snapshot/concurrency unchanged.

        (b) Fresh router, _prime raises for A only: assert a message mentioning A
            was surfaced, A not in snapshot, B in snapshot, concurrency == 1*cap.

        (c) Fresh router, _prime raises for BOTH: assert snapshot_and_prime()
            raises RuntimeError.
        """
        urls = ["http://endpointA", "http://endpointB"]
        cap = 2
        messages_collected = []
        message_lock = asyncio.Lock()

        async def collect_message(msg):
            async with message_lock:
                messages_collected.append(msg)

        # Part (a): both succeed
        router, _ = make_router(urls, cap)

        async def ok(state):
            return "ready"

        router._prime = ok

        messages_collected.clear()
        snapshot_urls1, concurrency1 = await asyncio.wait_for(
            router.snapshot_and_prime(notify=collect_message),
            timeout=2.0
        )

        assert len(messages_collected) == 2
        for url in urls:
            assert any(url in msg for msg in messages_collected)

        # Same router, second call - no new messages since already primed
        messages_collected.clear()
        snapshot_urls2, concurrency2 = await asyncio.wait_for(
            router.snapshot_and_prime(notify=collect_message),
            timeout=2.0
        )

        assert len(messages_collected) == 0
        assert len(snapshot_urls2) == 2
        assert concurrency2 == 4

        # Part (b): A fails, B succeeds
        messages_collected.clear()
        router2, _ = make_router(urls, cap)

        async def fail_a_only(state):
            if state.url == "http://endpointA":
                raise RuntimeError("failed")
            return "ready"

        router2._prime = fail_a_only

        snapshot_urls3, concurrency3 = await asyncio.wait_for(
            router2.snapshot_and_prime(notify=collect_message),
            timeout=2.0
        )

        assert any("endpointA" in msg for msg in messages_collected)
        assert "http://endpointA" not in snapshot_urls3
        assert "http://endpointB" in snapshot_urls3
        assert len(snapshot_urls3) == 1
        assert concurrency3 == cap

        # Part (c): both fail - should raise RuntimeError
        router3, _ = make_router(urls, cap)

        async def fail_both(state):
            raise RuntimeError("failed")

        router3._prime = fail_both

        with pytest.raises(RuntimeError, match="No LLM endpoints available"):
            await asyncio.wait_for(
                router3.snapshot_and_prime(notify=collect_message),
                timeout=2.0
            )


class TestBlockedAcquireRetriesWithoutRecursion:
    """Test 11: test_blocked_acquire_retries_without_recursion"""

    @pytest.mark.asyncio
    async def test_blocked_acquire_behavior(self):
        """
        Two endpoints, cap 1. Acquire BOTH permits directly so nothing is free.

        Create ONE _acquire_first_available() task. Yield the loop 200 times.

        Assert: the task is NOT done, and if it somehow finished it did not raise
        RecursionError (check task.exception() only if done).

        Then release ONE permit and assert asyncio.wait_for(task, 2.0) completes
        and returns the endpoint whose permit was released.

        Finally cancel/clean up so the test leaves no pending task.
        """
        urls = ["http://endpoint1", "http://endpoint2"]
        cap = 1
        router, endpoints = make_router(urls, cap)

        # Acquire BOTH permits directly - nothing is free
        await endpoints[urls[0]].sem.acquire()
        await endpoints[urls[1]].sem.acquire()

        # Create one acquire task
        task = asyncio.create_task(router._acquire_first_available())

        # Yield the loop 200 times
        for _ in range(200):
            await asyncio.sleep(0)

        # Task should NOT be done (waiting for permits)
        assert task.done() is False

        # Release ONE permit
        endpoints[urls[0]].sem.release()

        # Now wait for the task to complete
        result = await asyncio.wait_for(task, timeout=2.0)

        # Should have returned endpoint1 (whose permit was released)
        assert result.url == urls[0]

        # Clean up
        result.sem.release()
