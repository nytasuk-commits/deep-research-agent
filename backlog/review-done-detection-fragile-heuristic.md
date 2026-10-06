# Phase 3 review-done detection is a substring scan over all events

**Status:** Open
**Type:** Backlog (robustness + efficiency)
**Derived from:** `docs/reviews/2026-09-07/todo.md` item 8

## Problem

Review completion is detected by scanning **all** accumulated `_session_events` for the substring `"Reviewer"` inside `delegate_tasks` arguments (`tui.py:1124-1127`), on every agent-turn completion. Two issues:

1. **Any mention counts.** A task whose *instructions* contain the word "Reviewer" (e.g. "fix what the Reviewer flagged") satisfies `review_done` without any Reviewer delegation having run — the mandatory-review gate can be satisfied by prose.
2. **O(events × arg length) per turn**, re-scanning the whole event list each time.

## Evidence

Verified 2026-10-06: `tui.py:1124-1131`. The headless path (`tui.py:1434`, `:1479`) keys off `"final_report.md" in str(result)` instead — a different fragile heuristic for the same question.

## Fix direction

The reviewer-output-format fix (closed-loop 2026-10-06) gives a robust signal to detect against: record an explicit review-completed flag when a `delegate_tasks` call with `agent_id == "Reviewer"` returns a result (the guard in `orchestrator.py` already classifies that result), rather than substring-scanning history. Pair with `bugs/tui-module-state-leaks-across-runs.md` — the flag should be a properly reset contextvar, not another module global.

## Related

- `bugs/reviewer-output-format-non-compliance.md` — the verdict contract this can key on.
- `bugs/tui-module-state-leaks-across-runs.md` — where the flag state should live.
