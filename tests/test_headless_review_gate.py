"""
Regression tests for the headless review-gate re-arm (backlog/review-done-detection-fragile-heuristic.md,
headless variant observed live 2026-10-07, session 2f9a47a8).

run_cli armed report_just_written on ANY function result containing the
substring "final_report.md". The Reviewer's own delegate result wrapper
("## Result for Review final_report.md ...") contains that substring, so a
REVIEW PASSED round re-armed the gate for a pointless second round; the
Orchestrator then repeated the identical Reviewer delegation and tripped the
delegate_tasks identical-call loop breaker, force-terminating the turn.

Fix: arm only on the agent's OWN write of the report — a write_workspace_file
call whose arguments target final_report.md. Initial write arms round 1;
a correction edit arms round 2; a review verdict arms nothing.
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.tui import _headless_report_written, _ReportWriteTracker

TUI = Path(__file__).parent.parent / "src" / "engine" / "tui.py"


def test_write_of_report_arms_the_gate():
    assert _headless_report_written(
        "write_workspace_file", '{"file_path":"final_report.md","content":"# ..."}'
    ) is True


def test_write_with_full_path_arms():
    assert _headless_report_written(
        "write_workspace_file", '{"file_path":"run_123/final_report.md","content":"x"}'
    ) is True


def test_reviewer_delegate_call_does_not_arm():
    """The live repro: the Reviewer delegation (and by extension its result
    wrapper) must NOT re-arm the gate."""
    assert _headless_report_written(
        "delegate_tasks",
        '{"tasks":[{"agent_id":"Reviewer","instructions":"Review the file final_report.md"}]}',
    ) is False


def test_other_tool_call_does_not_arm():
    assert _headless_report_written("read_workspace_file", '{"file_path":"final_report.md"}') is False
    assert _headless_report_written("web_search", '{"query":"final_report.md review"}') is False
    assert _headless_report_written("write_workspace_file", '{"file_path":"notes.md","content":"x"}') is False
    assert _headless_report_written("think_tool", None) is False


# --- streaming-delta tracker (the real stream shape, instrumented run 2026-10-07) ---
# The framework streams a function call as: content(call_id, name, arguments="")
# then a nameless delta content(call_id=None, arguments=<full JSON>) that
# log_stream_content appends to the logged entry. Arming on the call content
# alone sees only the empty-args snapshot (DEBUG: argslen=0). The tracker
# accumulates per call_id and answers only once the RESULT arrives.

def test_tracker_arms_on_result_of_write_with_streamed_delta_args():
    t = _ReportWriteTracker()
    t.on_call("c1", "write_workspace_file", "")          # name arrives, args empty
    t.on_call(None, None, '{"filename":"final_report.md","content":"# x"}')  # delta
    assert t.report_written("c1") is True


def test_tracker_does_not_arm_for_reviewer_delegate_result():
    t = _ReportWriteTracker()
    t.on_call("c2", "delegate_tasks", "")
    t.on_call(None, None, '{"tasks":[{"agent_id":"Reviewer","instructions":"Review final_report.md"}]}')
    assert t.report_written("c2") is False


def test_tracker_no_args_no_arm():
    t = _ReportWriteTracker()
    t.on_call("c3", "write_workspace_file", "")
    assert t.report_written("c3") is False


def test_tracker_unknown_call_id_no_arm():
    t = _ReportWriteTracker()
    assert t.report_written("nope") is False


def test_run_cli_no_longer_scans_results_for_substring():
    """The fragile heuristic must be gone from the stream loop."""
    src = TUI.read_text(encoding="utf-8")
    assert '"final_report.md" in str(result)' not in src, (
        "run_cli still arms the review gate from result substrings"
    )


def test_run_cli_arms_from_write_call_helper():
    tree = ast.parse(TUI.read_text(encoding="utf-8"))
    run_cli = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "run_cli"
    )
    dumped = ast.dump(run_cli)
    assert "_ReportWriteTracker" in dumped, "run_cli does not use the streaming write-call tracker"
