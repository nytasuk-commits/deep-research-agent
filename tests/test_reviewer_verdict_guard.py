"""
Unit tests for engine.orchestrator._reviewer_verdict_issue.

This is the code-side guard for bugs/reviewer-output-format-non-compliance: the
Reviewer's verdict must be a numbered list or the verbatim REVIEW PASSED line,
but it has historically returned bullets or a leaked tool-call block and been
consumed silently. _reviewer_verdict_issue returns a human-readable reason for a
non-conforming verdict (or None when it conforms) so the consuming Orchestrator
and the session log see the failure instead of it quietly degrading.

These tests pin the classifier so a future edit that loosens or retightens the
conformance rules fails loudly here.

Note: the leak test builds its angle-bracket tokens at runtime from chr(60) and
chr(47). Those tokens are the same ones this harness uses to serialize tool
calls, so they cannot appear verbatim anywhere in a tool payload - even inside a
file's source, a comment, or a docstring - without being misparsed as a live
call. Building them at runtime keeps the runtime value intact (the guard's regex
still matches) while keeping the stream clean.
"""

import sys
from pathlib import Path

# Add src/ to path so imports work correctly
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.orchestrator import _reviewer_verdict_issue


def test_review_passed_line_is_compliant():
    assert _reviewer_verdict_issue("REVIEW PASSED: no integrity violations found.") is None


def test_numbered_list_is_compliant():
    verdict = (
        '1. Rule 4 (Sourcing): "59-62 tokens/sec" in the Executive Summary - '
        "time-sensitive figure with no date marker.\n"
        "2. Rule 8 (No unsourced data): the forecast table cites an unattributed CAGR."
    )
    assert _reviewer_verdict_issue(verdict) is None


def test_numbered_list_with_ellipsis_style_markers_is_compliant():
    verdict = "1. Rule 1: invented figure.\n2. Rule 2: missing date.\n3. Rule 3: unsourced."
    assert _reviewer_verdict_issue(verdict) is None


def test_bullet_verdict_is_flagged_as_bullets():
    verdict = (
        '- Rule 4: "59-62 tokens/sec" has no date marker.\n'
        "- Rule 8: the forecast table cites an unattributed CAGR."
    )
    issue = _reviewer_verdict_issue(verdict)
    assert issue is not None
    assert "bullets" in issue


def test_leaked_tool_call_block_is_flagged_as_a_leak():
    # Tokens built at runtime from chr(60)/chr(47) so the raw payload never
    # carries the harness's tool-call opening/closing tokens verbatim (see note).
    lt = chr(60)
    slash = chr(47)
    fn_open = lt + "function=think_tool>"
    param_open = lt + "parameter=reflection>"
    param_close = lt + slash + "parameter>"
    fn_close = lt + slash + "function>"
    verdict = (
        "Here is my review:\n"
        + fn_open + "\n"
        + param_open + "\n"
        + "The report has an unsourced figure...\n"
        + param_close + "\n"
        + fn_close
    )
    issue = _reviewer_verdict_issue(verdict)
    assert issue is not None
    assert "leaked" in issue


def test_narrated_prose_is_flagged_as_not_numbered():
    verdict = (
        "I reviewed the report. The Executive Summary contains a time-sensitive "
        "figure without a date marker, and the forecast table cites an unattributed CAGR."
    )
    issue = _reviewer_verdict_issue(verdict)
    assert issue is not None
    assert "numbered list" in issue


def test_empty_verdict_is_flagged():
    assert "empty" in _reviewer_verdict_issue("")
    assert "empty" in _reviewer_verdict_issue("   \n  ")


def test_numbered_list_that_also_contains_bullets_is_flagged():
    # Starts numbered but mixes in a dash bullet - the guard must not let that pass.
    verdict = "1. Rule 4: unsourced figure.\n- and one more in bullet form."
    issue = _reviewer_verdict_issue(verdict)
    assert issue is not None
    assert "bullets" in issue
