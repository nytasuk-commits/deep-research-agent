"""
Regression tests for bugs/review-gate-skipped-after-first-turn.md.

The mandatory-review gate computed review_done by scanning ALL accumulated
_session_events for "Reviewer" in delegate_tasks arguments. _session_events
persists across turns in one process, so turn 1's Reviewer delegation
satisfied the gate for every later turn: reports 2..N were written and
presented unreviewed. Live repro: session 9f3b80f8 (2026-10-06), turn 2's
final_report.md never reviewed.

Fix: the gate must consider only events from the current turn onward.
_turn_review_done(events, turn_start_idx) is the pure helper; the run_agent
wrapper records the turn-start index.
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.tui import _turn_review_done

TUI = Path(__file__).parent.parent / "src" / "engine" / "tui.py"


def _reviewer_event():
    return {"type": "function_call", "data": {
        "name": "delegate_tasks",
        "arguments": '{"tasks":[{"agent_id":"Reviewer","instructions":"Review final_report.md"}]}',
    }}


def _plain_event():
    return {"type": "function_call", "data": {"name": "web_search", "arguments": '{"query":"x"}'}}


def test_reviewer_from_a_previous_turn_does_not_satisfy_the_gate():
    """The live repro: turn 1's Reviewer sits before turn 2's start index,
    so turn 2's gate must be CLOSED (review_done False -> enforcement fires)."""
    events = [_plain_event(), _reviewer_event(), _plain_event()]
    assert _turn_review_done(events, turn_start_idx=2) is False


def test_reviewer_within_the_current_turn_satisfies_the_gate():
    events = [_plain_event(), _reviewer_event()]
    assert _turn_review_done(events, turn_start_idx=0) is True


def test_no_reviewer_anywhere_leaves_gate_closed():
    events = [_plain_event(), _plain_event()]
    assert _turn_review_done(events, turn_start_idx=0) is False


def test_events_without_delegate_args_are_skipped():
    events = [{"type": "text", "data": {"text": "Reviewer looks good"}}, _reviewer_event()]
    assert _turn_review_done(events, turn_start_idx=1) is True
    assert _turn_review_done(events, turn_start_idx=0) is True  # text event has no args


def test_run_agent_wrapper_records_turn_start_index():
    """Wiring guard: the run_agent wrapper must snapshot the event count so
    the gate can scope its scan to the current turn."""
    tree = ast.parse(TUI.read_text(encoding="utf-8"))
    run_agent = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "run_agent"
    )
    dumped = ast.dump(run_agent)
    assert "_turn_start_idx" in dumped, "run_agent wrapper does not record the turn-start index"
    assert "_turn_review_done" in dumped or "_turn_start_idx" in dumped


def test_gate_call_site_uses_scanned_scope():
    """The enforcement site must call _turn_review_done rather than scanning
    the full event list inline."""
    src = TUI.read_text(encoding="utf-8")
    assert "_turn_review_done(" in src, "gate does not use the per-turn helper"
