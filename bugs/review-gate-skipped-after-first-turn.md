# Mandatory review fires only on the first turn of a session

**Status:** FIXED 2026-10-06 and live-validated. `_turn_review_done(events, turn_start_idx)` scopes the gate scan to the current turn; the `run_agent` wrapper snapshots `self._turn_start_idx`. Pinned by `tests/test_review_gate_per_turn.py` (6 cases incl. the repro). Validation: session `c57d2d55`, one process, two report turns — turn 1 review at event 105, turn 2 review at event 459 (impossible pre-fix: turn 1's Reviewer satisfied the old whole-history scan). Suite: 40 passed.
**Severity:** High — the mandatory-review guarantee, the core of Phase 3, silently stops applying to every turn after the first in a process. Reports 2..N are written and presented unreviewed with no signal to the user.
**Derived from:** `backlog/review-done-detection-fragile-heuristic.md`, which predicted this; observed live for the first time 2026-10-06.

## Symptom

Session `9f3b80f8`, one TUI process, two turns:

- **Turn 1** (RTX 3060 vs RX 7600 XT price report): review enforced correctly — SYSTEM injection, Reviewer delegation, compliant numbered verdict, corrections applied.
- **Turn 2** (Qwen3-32B / Mistral Small 3 / Gemma 3 27B on RX 7900 XTX): `final_report.md` written (4899 bytes, workspace `run_1791303817`) and presented as final with **no review round at all** — no SYSTEM injection, no Reviewer delegation.

## Root cause

The enforcement check (`tui.py:1124-1131`) computes `review_done` by scanning **all accumulated `_session_events`** for the substring `"Reviewer"` inside `delegate_tasks` arguments. `_session_events` persists across turns in one process, so turn 1's Reviewer delegation satisfies the gate for every later turn. The check cannot distinguish "this turn's report was reviewed" from "some turn's report was reviewed."

## Fix direction

Scope the review-done signal to the current turn: reset the marker at turn start (the `run_agent` wrapper added by the review_phase_ctx fix is the natural place), or better, set an explicit per-turn flag when a Reviewer result is produced (the guard in `orchestrator.py` already identifies that result) instead of substring-scanning history. Either way the state must be per-turn, not per-process.

Pin with a test before fixing: two simulated turns where turn 1 contains a Reviewer delegation must still leave turn 2's gate closed.

## Related

- `backlog/review-done-detection-fragile-heuristic.md` — the prediction; update to point here.
- `bugs/tui-module-state-leaks-across-runs.md` — same class: per-process state where per-turn state is required.
