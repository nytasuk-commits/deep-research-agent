"""
Unit tests for src/tools/web.py web_search backoff behavior.

This test verifies that asyncio.sleep is never called while holding _backoff_lock.
The bug was: async with _backoff_lock: await asyncio.sleep(wait)
which made concurrent agents queue behind each other's sleeps and stall the pipeline.

Fix: The lock guards only the deadline update; sleep happens outside the lock.
"""

import sys
from pathlib import Path

# Add src/ to path so imports work correctly
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import asyncio
from unittest.mock import patch, MagicMock

import pytest


@pytest.mark.asyncio
async def test_web_search_backoff_does_not_hold_lock_during_sleep():
    """
    Verify that web_search never calls asyncio.sleep while holding _backoff_lock.

    Patch the ddgs client's text() method to always raise a generic exception
    (not "No results found." which returns early before backoff).

    Patch asyncio.sleep with an async function that records whether _backoff_lock
    is locked at each call, then returns immediately without awaiting anything real.
    The test must complete in milliseconds - the 30s and 60s waits must never elapse.

    Assertions:
      1. backoff ran (recorded list non-empty), else test proves nothing.
      2. Every recorded value is False - True would mean sleep ran while lock held.
      3. Exactly 2 entries since max_attempts=3 and backoff runs on attempts 0 and 1.
    """
    import tools.web as web

    # Reset module-level globals that affect the test
    web._consecutive_search_failures = 0
    web._next_allowed_search = 0.0

    recorded_lock_states = []

    async def patched_sleep(delay):
        """Record lock state, then return immediately without awaiting anything real."""
        recorded_lock_states.append(web._backoff_lock.locked())
        # Return immediately - no real await, test completes in milliseconds

    # Create a mock DDGS client that raises a generic exception
    mock_client = MagicMock()
    mock_client.text.side_effect = RuntimeError("Simulated search failure for testing backoff")
    mock_client.news.side_effect = RuntimeError("Simulated search failure for testing backoff")

    with patch.object(asyncio, 'sleep', side_effect=patched_sleep):
        with patch('tools.web.get_ddgs_client', return_value=mock_client):
            # Run one web_search call - it will hit the backoff logic
            await web.web_search("test query", max_results=5)

    # Assertion 1: backoff must have run at least once
    assert len(recorded_lock_states) > 0, \
        "backoff never ran — the test proves nothing"

    # Assertion 2: every recorded value must be False (lock not held during sleep)
    for i, is_locked in enumerate(recorded_lock_states):
        assert is_locked is False, \
            f"Record {i}: asyncio.sleep was called while _backoff_lock was locked (True). " \
            f"This means concurrent agents would queue behind each other's sleeps."

    # Assertion 3: exactly 2 entries (max_attempts=3, backoff on attempts 0 and 1 only)
    assert len(recorded_lock_states) == 2, \
        f"Expected exactly 2 backoff calls (for attempts 0 and 1), got {len(recorded_lock_states)}"
