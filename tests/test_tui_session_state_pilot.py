"""Pilot tests: drive the real BasicTuiAgent headlessly to prove session
state isolation across /new and /resume in one process — the live-equivalent
validation for bugs/tui-module-state-leaks-across-runs.md defect 3
(user-approved 2026-10-07).

Async drivers run inside asyncio.run() from sync test functions:
pytest-asyncio strict mode is not configured in this repo.
"""

import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

import config
from engine import session_log
import engine.orchestrator as orchestrator_module
from engine.sdk import AgentBuilder
from engine.tui import BasicTuiAgent


@pytest.fixture(autouse=True)
def _no_persistence(monkeypatch):
    monkeypatch.setitem(config.cfg["settings"], "enable_session_persistence", False)


@pytest.fixture(autouse=True)
def _fresh_state():
    """_session_state is process-global; other test files (e.g.
    test_session_log_state.py's wrapper test) log into it. Swap in a fresh
    object before and after each pilot test so suite ordering cannot leak
    events into the isolation assertions."""
    session_log.new_session()
    yield
    session_log.new_session()


def _builder():
    return AgentBuilder(name="test", description="d", instructions="i", tools=[])


class _NoAgentTui(BasicTuiAgent):
    """Auto-prime (on_mount schedules run_agent("Hello") at +0.1s) and real
    agent turns are out of scope for state-isolation tests. The override is
    sync to match the @work calling convention."""

    def run_agent(self, query, show_user_message=True):
        return None


def test_new_command_swaps_the_state_object():
    async def drive():
        app = _NoAgentTui(_builder())
        async with app.run_test() as pilot:
            session_log.log_stream_content("Agent", "text", {"text": "run one"})
            old = session_log._session_state
            assert old.events

            await pilot.click("#prompt-input")
            # Textual 8.2.8 Pilot has no type(); press the keys one by one.
            await pilot.press("/", "n", "e", "w")
            await pilot.press("enter")
            await pilot.pause()

            new = session_log._session_state
            assert new is not old
            assert new.events == []
            assert new.session_id != old.session_id
            # the old run's log is unreachable from the live pointer and
            # was not mutated by the swap
            assert old.events[0]["data"]["text"] == "run one"

    asyncio.run(drive())


def test_resume_loads_saved_log_into_fresh_state():
    sid = "test-" + uuid.uuid4().hex[:8]
    log_dir = Path.home() / f".{config.APP_NAME}" / "sessions"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"session_{sid}.json"
    saved = {
        "timestamp": "2026-10-07T00:00:00",
        "ui_events": [{"timestamp": "t", "source": "User", "type": "prompt",
                       "data": {"text": "restored"}}],
        "agent_session": None,
        "session_id": sid,
    }
    log_file.write_text(json.dumps(saved), encoding="utf-8")

    async def fake_create_local_agent(builder=None, subagent_callback=None,
                                      session_data=None, notify=None):
        return None, None

    async def drive():
        app = _NoAgentTui(_builder())
        async with app.run_test() as pilot:
            session_log.log_stream_content("Agent", "text", {"text": "current run"})
            old = session_log._session_state
            await app._load_session_by_id(sid)
            await pilot.pause()
            st = session_log._session_state
            assert st is not old
            assert st.session_id == sid
            assert [e["data"]["text"] for e in st.events] == ["restored"]

    orig = orchestrator_module.create_local_agent
    orchestrator_module.create_local_agent = fake_create_local_agent
    try:
        asyncio.run(drive())
    finally:
        orchestrator_module.create_local_agent = orig
        log_file.unlink(missing_ok=True)
