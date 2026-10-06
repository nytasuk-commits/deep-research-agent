# TUI module-level state and contextvars leak across runs in one process

**Status:** Defect 1 FIXED 2026-10-06 (`end_review_phase()` in core.py, called in a finally on both turn-end paths — `run_agent` wrapper in the TUI, `run_cli` finally in headless; pinned by `tests/test_review_phase_reset.py`, 6 cases incl. AST wiring guards). Defect 2 reclassified (see below). Defect 3 open. NOT yet validated on a live multi-run session.
**Severity:** Medium-High (was) — after the first review phase, `review_phase_ctx` stayed `True` for the rest of the process, permanently releasing the `web_calls` reserve that is supposed to be held back; run N+1 via `/new` inherited it
**Derived from:** `docs/reviews/2026-09-07/todo.md` item 3. Distinct from `backlog/search-module-level-state.md` (web.py only).

## Defects (verified 2026-10-06 against current code)

1. **`review_phase_ctx` never reset.** Set `True` at `tui.py:1134` (TUI) and `tui.py:1484` (headless) when review is enforced; no `reset()` anywhere in `src/`. `core.py:36` releases the `web_calls` reserve whenever `review_phase_ctx.get()` is true — so once any run in the process enters review, every later run gets the reserve budget it should not have. This is the concrete "wrong review enforcement" the todo predicted.
2. **`session_dir_ctx` token never reset in the TUI path — RECLASSIFIED 2026-10-06, do NOT "fix" by resetting at turn end.** Set per agent-turn at `tui.py:900` (inside `run_agent`) with no reset; the headless path sets at `:1268` and resets at `:1511-1513`. On inspection the TUI non-reset is *load-bearing*: `/files` and the workspace tools resolve paths through `session_dir_ctx.get()` (`fs.py:25`), so clearing it at turn end would make `/files` look in the workspace root instead of the current run folder. The real oddity is the opposite of a leak: the set happens **per turn**, so a multi-turn session scatters its turns across different `run_<ts>/` folders. Whether one folder per session is intended is a design question, not a state leak — left open.
3. **Module-level mutable globals** at `tui.py:26-29` (`_session_events`, `_current_call_by_source`, `_current_text_by_source`, `_current_session_id`). `/new` (`tui.py:555-564`) does clear the three containers and re-ids the session — so the todo's "run N+1 inherits run N's state" is **partially stale** for the globals — but they remain process-global mutable state shared by `/resume` (`:649`, `:1330`) and every writer (`_log_event` at `:60-85`), with no ownership discipline. The contextvar leaks (1, 2) are the live defect; the globals are the structural hazard.

## Fix direction

Defect 1 fixed as above. Remaining: defect 3 (fold the globals into a per-run state object) and the defect-2 design question (one run folder per session vs per turn). The original "reset both contextvars at run end" direction was wrong for defect 2 — see the reclassification.

## Related

- `backlog/search-module-level-state.md` — the web.py counterpart, already tracked.
- `backlog/review-done-detection-fragile-heuristic.md` — same review-gate machinery.
