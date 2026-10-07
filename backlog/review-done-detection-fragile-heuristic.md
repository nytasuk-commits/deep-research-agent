# Phase 3 review-done detection is a substring scan over all events

**Status:** TUI half fixed (`bugs/review-gate-skipped-after-first-turn.md`, 76ecc86). **Headless half FIXED 2026-10-07, live-validated** — the gate now arms on the RESULT of a `write_workspace_file` call targeting `final_report.md`, tracked per call_id by `_ReportWriteTracker`; pinned by `tests/test_headless_review_gate.py` (10 cases). Live (session `c533c138`): round 1 armed on the real write through the streaming-delta shape, a second real write armed round 2, a third write after exhaustion armed nothing, clean exit — one enforcement per write, no runaway. The REVIEW-PASSED-with-no-rewrite negative case was not live-observed (the reviewer endpoint 500'd both rounds) but is unit-pinned; mechanistically airtight since a `delegate_tasks` call_id can never satisfy the write predicate.

**Streaming-delta trap found during the fix (2026-10-07, instrumented run):** the framework streams a function call as `content(call_id, name, arguments="")` followed by a nameless delta `content(call_id=None, arguments=<JSON>)`; `log_stream_content` appends the delta into the logged entry (tui.py:150), so the SESSION LOG shows complete arguments while any stream-loop consumer sees `argslen=0` on the named content. A first attempt at this fix armed on the call content and silently never fired the gate at all (validation run caught it: report written, zero review rounds). Any headless code that keys on call arguments must accumulate deltas per call_id and evaluate at the function_result, which is what `_ReportWriteTracker` does. The TUI path is immune — `_turn_review_done` reads the merged `_session_events`, not raw stream content.
**Type:** Backlog (robustness + efficiency)
**Derived from:** `docs/reviews/2026-09-07/todo.md` item 8

## Problem

Review completion is detected by scanning **all** accumulated `_session_events` for the substring `"Reviewer"` inside `delegate_tasks` arguments (`tui.py:1124-1127`), on every agent-turn completion. Two issues:

1. **Any mention counts.** A task whose *instructions* contain the word "Reviewer" (e.g. "fix what the Reviewer flagged") satisfies `review_done` without any Reviewer delegation having run — the mandatory-review gate can be satisfied by prose.
2. **O(events × arg length) per turn**, re-scanning the whole event list each time.

## Evidence

Verified 2026-10-06: `tui.py:1124-1131`. The headless path (`tui.py:1434`, `:1479`) keys off `"final_report.md" in str(result)` instead — a different fragile heuristic for the same question.

**Headless variant observed live 2026-10-07, session `2f9a47a8`:** round 1's Reviewer verdict was the verbatim `REVIEW PASSED` line, but the delegate result's own wrapper (`## Result for Review final_report.md ...`) contains the substring `final_report.md`, so `"final_report.md" in str(result)` re-armed the gate for a pointless round 2. The Orchestrator then repeated the identical Reviewer delegation, tripping the `delegate_tasks` identical-call loop breaker — the turn was force-terminated mid-review. The heuristic didn't just waste a round; it manufactured a loop-breaker abort.

## Fix direction

The reviewer-output-format fix (closed-loop 2026-10-06) gives a robust signal to detect against: record an explicit review-completed flag when a `delegate_tasks` call with `agent_id == "Reviewer"` returns a result (the guard in `orchestrator.py` already classifies that result), rather than substring-scanning history. Pair with `bugs/tui-module-state-leaks-across-runs.md` — the flag should be a properly reset contextvar, not another module global.

## Related

- `bugs/reviewer-output-format-non-compliance.md` — the verdict contract this can key on.
- `bugs/tui-module-state-leaks-across-runs.md` — where the flag state should live.
