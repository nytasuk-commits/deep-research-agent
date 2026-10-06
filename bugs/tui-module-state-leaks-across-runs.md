# TUI module-level state and contextvars leak across runs in one process

**Status:** Open
**Severity:** Medium-High — after the first review phase, `review_phase_ctx` stays `True` for the rest of the process, permanently releasing the `web_calls` reserve that is supposed to be held back; run N+1 via `/new` inherits it
**Derived from:** `docs/reviews/2026-09-07/todo.md` item 3. Distinct from `backlog/search-module-level-state.md` (web.py only).

## Defects (verified 2026-10-06 against current code)

1. **`review_phase_ctx` never reset.** Set `True` at `tui.py:1134` (TUI) and `tui.py:1484` (headless) when review is enforced; no `reset()` anywhere in `src/`. `core.py:36` releases the `web_calls` reserve whenever `review_phase_ctx.get()` is true — so once any run in the process enters review, every later run gets the reserve budget it should not have. This is the concrete "wrong review enforcement" the todo predicted.
2. **`session_dir_ctx` token never reset in the TUI path.** Set per agent-turn at `tui.py:900` (inside `run_agent`) with no reset; the headless path sets at `:1268` and correctly resets at `:1511-1513`. The TUI path leaves the last run folder bound in the context.
3. **Module-level mutable globals** at `tui.py:26-29` (`_session_events`, `_current_call_by_source`, `_current_text_by_source`, `_current_session_id`). `/new` (`tui.py:555-564`) does clear the three containers and re-ids the session — so the todo's "run N+1 inherits run N's state" is **partially stale** for the globals — but they remain process-global mutable state shared by `/resume` (`:649`, `:1330`) and every writer (`_log_event` at `:60-85`), with no ownership discipline. The contextvar leaks (1, 2) are the live defect; the globals are the structural hazard.

## Fix direction

Reset both contextvars at run end (mirror the headless `:1511-1513` pattern in the TUI path), and reset `review_phase_ctx` when the review round completes or the turn ends. Consider folding the three globals into a per-run state object.

## Related

- `backlog/search-module-level-state.md` — the web.py counterpart, already tracked.
- `backlog/review-done-detection-fragile-heuristic.md` — same review-gate machinery.
