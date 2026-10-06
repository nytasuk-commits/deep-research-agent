# QuotaAbortException inherits BaseException, bypassing ordinary handlers

**Status:** Open
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

## Fix direction

Make it `Exception` and give the `@with_quota` wrapper an explicit `except QuotaAbortException: raise` **before** its generic handler, so the abort still unwinds while ordinary handlers can catch it normally. Replace the `tui.py:1439` string check with a real catch. Validate on a run that actually trips a quota abort.

## Related

- `backlog/loop-breaker-evasion-varied-greps.md` — same quota/loop-breaker machinery in core.py.
