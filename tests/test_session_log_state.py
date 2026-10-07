"""Unit tests for engine/session_log.py — the per-session state object
extracted from tui.py (bugs/tui-module-state-leaks-across-runs.md defect 3).

No Textual import: the class must be testable on its own. Streaming
accumulation semantics are the pre-existing tui.py behaviour, pinned here
so the verbatim move is provably behaviour-preserving.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

import config
from engine import session_log
from engine.session_log import SessionLogState, new_session, load_session, begin_turn


@pytest.fixture(autouse=True)
def _no_persistence(monkeypatch):
    """Never write real session files from unit tests, regardless of the
    user's config. Patch the config module session_log actually holds —
    sys.modules['config'] can be a mock from another test file."""
    from engine import session_log as _sl
    monkeypatch.setitem(_sl.config.cfg["settings"], "enable_session_persistence", False)


def test_text_continuation_merges_into_open_entry():
    st = SessionLogState()
    st.log_stream_content("Agent", "text", {"text": "Hello "})
    st.log_stream_content("Agent", "text", {"text": "world"})
    assert len(st.events) == 1
    assert st.events[0]["data"]["text"] == "Hello world"


def test_nameless_call_delta_appends_to_open_call_arguments():
    st = SessionLogState()
    st.log_stream_content("Agent", "function_call",
                          {"call_id": "c1", "name": "web_search", "arguments": "{"})
    st.log_stream_content("Agent", "function_call",
                          {"call_id": None, "arguments": '"q":"x"}'})
    assert len(st.events) == 1
    assert st.events[0]["data"]["arguments"] == '{"q":"x"}'


def test_function_result_closes_accumulators():
    st = SessionLogState()
    st.log_stream_content("Agent", "text", {"text": "hi"})
    st.log_stream_content("Agent", "function_result", {"call_id": "c1", "result": "ok"})
    st.log_stream_content("Agent", "text", {"text": " again"})
    assert len(st.events) == 3
    assert st.events[2]["data"]["text"] == " again"


def test_log_prompt_clears_accumulators_and_appends():
    st = SessionLogState()
    st.log_stream_content("Agent", "text", {"text": "partial"})
    st.log_prompt("next turn")
    assert st.events[-1]["type"] == "prompt"
    assert st.current_text_by_source == {}
    assert st.current_call_by_source == {}


def test_write_log_skips_when_persistence_off():
    st = SessionLogState()
    st.log_prompt("x")  # log_prompt calls write_log; must not raise or write
    assert st.events[0]["data"]["text"] == "x"


def test_new_session_swaps_pointer_and_leaves_old_object_intact():
    old = session_log._session_state
    old.log_prompt("keep me")
    st = new_session()
    assert session_log._session_state is st
    assert st is not old
    assert st.events == []
    assert st.session_id != old.session_id
    assert old.events[0]["data"]["text"] == "keep me"


def test_load_session_owns_the_saved_list():
    data = {"ui_events": [{"source": "User", "type": "prompt", "data": {"text": "restored"}}]}
    st = load_session(data, "abc")
    assert session_log._session_state is st
    assert st.session_id == "abc"
    assert st.events is data["ui_events"]


def test_begin_turn_snapshots_event_index():
    new_session()
    session_log.log_prompt("t1")
    begin_turn()
    assert session_log._session_state.turn_start_idx == 1
    session_log.log_prompt("t2")
    begin_turn()
    assert session_log._session_state.turn_start_idx == 2


def test_wrappers_delegate_through_the_current_pointer():
    st = new_session()
    session_log.log_prompt("through wrapper")
    session_log.log_stream_content("Agent", "text", {"text": "streamed"})
    session_log._write_log()
    assert st.events[0]["data"]["text"] == "through wrapper"
    assert st.events[1]["data"]["text"] == "streamed"


# --- run_dir: one workspace run folder per session, not per turn
# (bugs/tui-module-state-leaks-across-runs.md defect 2) ---


def test_new_state_mints_run_dir():
    st = SessionLogState()
    assert st.run_dir is not None
    assert st.run_dir.startswith("run_")
    assert st.run_dir[4:].isdigit()


def test_from_saved_reads_run_dir():
    st = SessionLogState.from_saved({"ui_events": [], "run_dir": "run_123"}, "sid")
    assert st.run_dir == "run_123"


def test_from_saved_without_run_dir_is_none():
    # Pre-fix session files have no run_dir key; resume must not silently
    # mint a different folder — ensure_run_dir() does that lazily.
    st = SessionLogState.from_saved({"ui_events": []}, "sid")
    assert st.run_dir is None


def test_ensure_run_dir_mints_lazily_when_none_and_is_stable():
    st = SessionLogState.from_saved({"ui_events": []}, "sid")
    d = st.ensure_run_dir()
    assert d is not None and d.startswith("run_")
    assert st.run_dir == d
    assert st.ensure_run_dir() == d


def test_ensure_run_dir_returns_the_saved_dir():
    st = SessionLogState.from_saved({"ui_events": [], "run_dir": "run_9"}, "sid")
    assert st.ensure_run_dir() == "run_9"


def test_write_log_round_trips_run_dir(tmp_path, monkeypatch):
    from engine import session_log as _sl
    monkeypatch.setitem(_sl.config.cfg["settings"], "enable_session_persistence", True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    st = SessionLogState()
    st.log_prompt("x")
    log_file = tmp_path / f".{config.APP_NAME}" / "sessions" / f"session_{st.session_id}.json"
    data = json.loads(log_file.read_text(encoding="utf-8"))
    assert data["run_dir"] == st.run_dir
    restored = SessionLogState.from_saved(data, st.session_id)
    assert restored.run_dir == st.run_dir


def test_run_dir_wrappers_delegate_through_the_current_pointer():
    st = new_session()
    assert session_log.ensure_run_dir() == st.run_dir
    assert session_log.current_run_dir() == st.run_dir
