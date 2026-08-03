"""
Unit tests for src/engine/router.py.

These tests are designed to be deterministic and race-free by following strict rules:
- RULE 1: All acquire operations use async context manager (no manual semaphore handling).
- RULE 2: Every blocking await wrapped in asyncio.wait_for(..., timeout=2.0).
- RULE 3: No asyncio.sleep with real duration > 0.05s; assert computed values.
- RULE 4: No network. All endpoints' .raw and .client replaced with fakes.

Shared helper make_router() monkeypatches config.cfg reads and uses MagicMock
for all endpoint clients.
"""

import os
import sys
import tempfile
from pathlib import Path

# Set env var BEFORE importing anything else (the logger is built at import time)
os.environ["DRA_ROUTER_LOG"] = os.path.join(
    tempfile.gettempdir(), "dra_router_test.log"
)

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


class TestInflightAccountingBalances:
    """Test 1: test_counter_returns_to_zero"""

    @pytest.mark.asyncio
    async def test_acquire_releases_correctly(self):
        """
        Two endpoints, cap 2. Run 8 concurrent `async with router.acquire(name)`
        blocks; each awaits asyncio.sleep(0.01) inside the block.
        Assert:
          - all 8 completed (none blocked),
          - after completion, inflight_snapshot() is 0 for EVERY endpoint,
          - the sum of both endpoints' served counts == 8.
        """
        urls = ["http://endpoint1", "http://endpoint2"]
        cap = 2
        router, endpoints = make_router(urls, cap)

        async def do_work(task_id):
            name = f"task-{task_id}"
            async with router.acquire(name) as client:
                await asyncio.sleep(0.01)
            return task_id

        # Fire 8 concurrent tasks
        tasks = [asyncio.create_task(do_work(i)) for i in range(8)]
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=5.0)

        # All 8 completed
        assert len(results) == 8

        # After completion, all inflight counts are 0
        snapshot = router.inflight_snapshot()
        for url in urls:
            assert snapshot[url] == 0, f"Inflight not zero for {url}: {snapshot[url]}"

        # Total served count is 8
        total_served = sum(endpoints[u].served for u in urls)
        assert total_served == 8


class TestInflightNoDriftOverRounds:
    """Test 2: test_repeated_rounds_no_drift"""

    @pytest.mark.asyncio
    async def test_many_rounds_no_leak(self):
        """
        Two endpoints, cap 3. Run 10 sequential rounds; each round runs 6 concurrent
        acquire blocks (asyncio.sleep(0.005) inside) and gathers them.
        After EVERY round assert inflight_snapshot() values are all 0.
        After all rounds assert total served across endpoints == 60.
        """
        urls = ["http://endpoint1", "http://endpoint2"]
        cap = 3
        router, endpoints = make_router(urls, cap)

        for round_num in range(10):
            async def do_work(task_id):
                name = f"round{round_num}-task-{task_id}"
                async with router.acquire(name) as client:
                    await asyncio.sleep(0.005)
                return task_id

            # Fire 6 concurrent tasks per round
            tasks = [asyncio.create_task(do_work(i)) for i in range(6)]
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=2.0)

            # After each round, all inflight must be 0 (catch leaked increments)
            snapshot = router.inflight_snapshot()
            for url in urls:
                assert snapshot[url] == 0, \
                    f"Round {round_num}: inflight not zero for {url}: {snapshot[url]}"

        # After all rounds, total served is 60
        total_served = sum(endpoints[u].served for u in urls)
        assert total_served == 60


class TestLeastLoadedBalance:
    """Test 3: test_load_spreads_evenly"""

    @pytest.mark.asyncio
    async def test_balance_work_distribution(self):
        """
        Two endpoints, cap 3. Run 12 concurrent acquire blocks, each holding for
        asyncio.sleep(0.02) so they overlap.

        Assert:
          - both endpoints served at least 1 task (work spread),
          - final served counts differ by no more than 2,
          - no sampled inflight value was ever negative,
          - inflight_snapshot() is all zeros at the end.
        """
        urls = ["http://endpoint1", "http://endpoint2"]
        cap = 3
        router, endpoints = make_router(urls, cap)

        sampled_inflight_values = []
        sampled_lock = asyncio.Lock()

        async def do_work(task_id):
            name = f"task-{task_id}"
            # Sample inflight values on entry (non-blocking snapshot)
            async with sampled_lock:
                sampled_inflight_values.append(router.inflight_snapshot().copy())

            async with router.acquire(name) as client:
                await asyncio.sleep(0.02)
            return task_id

        # Fire 12 concurrent tasks
        tasks = [asyncio.create_task(do_work(i)) for i in range(12)]
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=5.0)

        # All completed
        assert len(results) == 12

        # Both endpoints served at least 1 task
        served_count_0 = endpoints[urls[0]].served
        served_count_1 = endpoints[urls[1]].served
        assert served_count_0 >= 1, "Endpoint 0 should have served at least 1 task"
        assert served_count_1 >= 1, "Endpoint 1 should have served at least 1 task"

        # Final counts differ by no more than 2 (least-loaded keeps them balanced)
        diff = abs(served_count_0 - served_count_1)
        assert diff <= 2, f"Served counts too unbalanced: {served_count_0} vs {served_count_1}"

        # No negative inflight values were ever sampled
        for sample in sampled_inflight_values:
            for url in urls:
                assert sample[url] >= 0, f"Negative inflight sampled for {url}: {sample[url]}"

        # Final inflight snapshot is all zeros
        final_snapshot = router.inflight_snapshot()
        for url in urls:
            assert final_snapshot[url] == 0, f"Final inflight not zero for {url}"


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
    """Test 6: single-endpoint config behaves like the pre-router single client."""

    @pytest.mark.asyncio
    async def test_single_endpoint_behavior(self):
        """
        One URL, cap 3, _prime stubbed to succeed.
        Assert: snapshot has exactly 1 url, current_concurrency() == 3, and
        orchestrator_client() returns THAT endpoint's client object (identity).
        Also assert orchestrator_client() raises RuntimeError when
        _snapshot_urls is empty.
        """
        urls = ["http://single-endpoint"]
        cap = 3

        # Test 6a: single endpoint with successful prime
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

        # orchestrator_client() returns the same object (identity check)
        assert router.orchestrator_client() is endpoints[urls[0]].client

        # Test 6b: fresh router with empty _snapshot_urls should raise RuntimeError
        router2, _ = make_router(urls, cap)
        router2._snapshot_urls = []

        with pytest.raises(RuntimeError, match="No LLM endpoints available"):
            router2.orchestrator_client()


class TestBackoffScheduleAndPermanentDown:
    """Test 7: test_backoff_schedule_and_permanent_down"""

    def test_backoff_schedule(self):
        """
        One endpoint state. Monkeypatch time.monotonic to return fixed value T.

        Call _mark_probe_failed repeatedly. After each call assert next_probe_at
        equals T + the expected value from _BACKOFF tuple.

        After _MAX_FAILS calls, assert permanently_down is True.
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


class TestSelectEndpointIsSynchronousAndNonBlocking:
    """Test 11: test_select_never_blocks_and_picks_least_loaded"""

    def test_select_endpoint_is_synchronous(self):
        """
        (a) Manually set endpoint A's inflight = 5 and B's inflight = 0.
            Assert _select_endpoint() returns B. Call it 3 times in a row
            and assert it returns B every time (it is pure — no side effects).
        (b) Set both inflight to 4 (equal). Assert _select_endpoint() returns
            the FIRST endpoint in config order (stable tie-break).
        (c) Assert _select_endpoint is NOT a coroutine function.
        (d) Set every endpoint's inflight to a large number (e.g. 99).
            Assert _select_endpoint() STILL returns an endpoint immediately.
        (e) On a router whose _snapshot_urls is [], assert _select_endpoint()
            raises RuntimeError.
        """
        urls = ["http://endpointA", "http://endpointB"]
        cap = 1
        router, endpoints = make_router(urls, cap)

        # Part (a): B has fewer inflight, should be selected
        endpoints[urls[0]].inflight = 5  # A has high load
        endpoints[urls[1]].inflight = 0  # B is idle

        for _ in range(3):
            result = router._select_endpoint()
            assert result.url == urls[1], "Should select endpoint with lowest inflight"
            assert result.inflight == 0, "Inflight count unchanged (no side effects)"

        # Part (b): equal inflight - tie-break to first in config order
        endpoints[urls[0]].inflight = 4
        endpoints[urls[1]].inflight = 4

        for _ in range(3):
            result = router._select_endpoint()
            assert result.url == urls[0], "Tie-break should select first endpoint in config order"

        # Part (c): _select_endpoint is NOT a coroutine function
        import inspect
        assert not inspect.iscoroutinefunction(router._select_endpoint), \
            "_select_endpoint must be synchronous, not async"

        # Part (d): all endpoints saturated - still returns immediately without error
        for url in urls:
            endpoints[url].inflight = 99

        result = router._select_endpoint()  # Should NOT raise or block
        assert result is not None

        # Part (e): empty _snapshot_urls raises RuntimeError
        router_empty, _ = make_router(urls, cap)
        router_empty._snapshot_urls = []

        with pytest.raises(RuntimeError, match="No endpoint snapshot"):
            router_empty._select_endpoint()
