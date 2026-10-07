# QuotaAbortException inherits BaseException, bypassing ordinary handlers

**Status:** FIXED 2026-10-06, live-validated 2026-10-07 — but the original fix direction was WRONG and was corrected by a framework audit (see below). The base class stays `BaseException` (load-bearing); the string-name-check smell is removed and the invariant is pinned by tests.
**Severity:** Medium — cheap to fix now, expensive after more call sites accrete; any future `except Exception` around tool execution silently swallows a quota abort
**Derived from:** `docs/reviews/2026-09-07/todo.md` item 4

## Symptom

`core.py:25` declares `class QuotaAbortException(BaseException)`. Because it is not an `Exception`, every ordinary `except Exception` handler — including the `@with_quota` wrapper's own error path (`core.py:195`) — lets it pass through, and call sites have had to compensate in two different ways:

- proper catch: `tui.py:1028`, `orchestrator.py:245` (`except QuotaAbortException`)
- string-name check: `tui.py:1439` (`type(e).__name__ == "QuotaAbortException"`) — a smell that exists only because the class is not reliably catchable by type at that site.

## Evidence

Verified 2026-10-06: `core.py:25` (class), `core.py:48/:117/:162` (raise sites), the two catch styles above. `core.py:140-162` comments show the abort path is already delicate (a second `final_report.md` write raising deep in delegation).

## Root cause

Chosen, it appears, to escape the wrapper's `except Exception` → CRITICAL-error-string conversion so the abort can unwind to the run loop. That works but inverts the convention: BaseException is reserved for interpreter-level exits (KeyboardInterrupt, SystemExit), and every future call site must know to catch it explicitly.

## Fix direction (original) — DISPROVEN by framework audit 2026-10-06

The original direction — make it `Exception` and re-raise explicitly in the wrapper — would have **disabled the loop breaker**. Audit of agent-framework 1.12.1 (`venv/.../agent_framework/_tools.py`):

- `_auto_invoke_function` wraps every tool invocation with `except UserInputRequiredException: raise` / `except Exception as exc: return Content.from_function_result(result="Error: Function failed.", exception=str(exc))` — `_tools.py:1537` (direct path) and `:1613` (middleware path).
- Any `Exception` raised by a tool is therefore converted into an error **result** handed back to the model; it never reaches our salvage catches.
- `QuotaAbortException` inherits `BaseException` precisely to escape that conversion and unwind to the salvage handlers (`tui.py:1058` TUI loop, `orchestrator.py:284` delegation, `run_cli`).
- Other framework catches were checked and are safe either way: `FunctionTool.__call__` (`_tools.py:546`) catches Exception but re-raises; `invoke_with_termination_handling` catches only `MiddlewareTermination`/`UserInputRequiredException`; argument-parsing catches are `(TypeError, ValidationError)`.

Had the base class been switched, quota aborts would surface to the model as "Error: Function failed." strings, the model would keep looping — the exact failure the breaker exists to stop.

## Fix applied (2026-10-06)

1. **Base class kept** and the reason documented in the class docstring (`core.py:33`), with the framework version and line refs, plus a "revisit if the framework stops converting Exceptions" note.
2. **The actual defect removed**: `run_cli` detected the abort with `type(e).__name__ == "QuotaAbortException"` inside an `except BaseException` — replaced with a direct `except QuotaAbortException` (the class was already imported at `tui.py:21`; the string check was never needed). Behaviour is identical: same branch, same message, same `break`; other exceptions propagate exactly as before (the old handler re-raised them).

Pinned by `tests/test_quota_abort_exception_class.py` (3 cases): the base-class invariant (asserts NOT an Exception subclass, with the framework reason in the docstring — this is the guard that stops a future well-meaning "fix" from re-breaking the breaker), no string-name check anywhere in tui.py, and run_cli catches by type. The latter two watched RED first. Suite: 48 passed.

## Validation

**Live-validated 2026-10-07, headless session `2f9a47a8`** (`--auto-approve`, normal quotas). An organic abort fired at the refactored site: the headless review gate re-armed a second round (fragile heuristic — see `backlog/review-done-detection-fragile-heuristic.md`), the Orchestrator issued the identical Reviewer `delegate_tasks` twice, and `_check_repeat` raised. Console showed exactly the new branch's output — `[System] Task forcefully aborted: Agent trapped in identical-call loop: 'delegate_tasks' called with identical arguments 2 times in a row. Force-terminating turn.` — then the loop broke and the process exited cleanly ("Task completed in 859.8 seconds"). This simultaneously confirms: (a) the catch-by-type branch works, (b) the BaseException base still escapes agent-framework's Exception-to-error-result conversion, i.e. the corrected diagnosis holds in production.

## Related

- `backlog/loop-breaker-evasion-varied-greps.md` — same quota/loop-breaker machinery in core.py.
