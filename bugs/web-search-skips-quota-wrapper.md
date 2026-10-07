# web_search bypasses @with_quota, losing loop detection and the error wrapper

**Status:** Fix applied 2026-10-06, unit-pinned (5 tests, watched RED first); NOT yet live-validated — do not commit until a live session exercises it
**Severity:** Medium-High — the tool most prone to runaway loops is the one without loop protection
**Derived from:** `docs/reviews/2026-09-07/todo.md` item 5

## Symptom

`web.py:398` decorates `web_search` with `@tool` only — not `@with_quota`. It hand-rolls `check_quota("web_search")` at `web.py:417`, which covers the counter but skips everything the decorator adds (`core.py:191-196`):

- **`_check_repeat` loop detection** (`core.py:61`, window-based alternating-pattern detector) — never runs for `web_search`.
- **CRITICAL tool-execution error wrapper** — an internal exception in `web_search` propagates raw instead of becoming the standard diagnostic string every other tool returns.

## Evidence

Verified 2026-10-06: `web.py:398-419` (manual `check_quota`, no decorator), `core.py:185-207` (what `@with_quota` provides). The search-to-fetch ratio guard at `web.py:421+` exists precisely because observed runs burned ~20 searches in a row — the exact behaviour `_check_repeat` is designed to catch, and which `web_search` cannot currently catch.

## Root cause

`web_search` needs the `web_calls` pool logic (reserve/allocation) that plain `check_quota` provides, so it was wired manually — but the manual path duplicated only the counter, not the decorator's other two protections.

## Fix applied (2026-10-06)

`web.py:398` now carries `@tool` + `@with_quota` — the same stack `fetch_url_to_workspace` uses (`web.py:122-123`) — and the manual `check_quota("web_search")` block was removed so the pool is charged exactly once (by the decorator). The search-to-fetch ratio guard stays in the body; its `tool_quotas_ctx` import stays.

Behaviour changes for `web_search`:
- **Identical consecutive search → hard abort.** Second identical call raises `QuotaAbortException` via `_check_repeat` (threshold 1, window detector at 4-in-12 for alternating patterns); the salvage-on-abort path returns partial work. `web_search` is not in `_READ_ONLY_TOOLS`, so it gets the same treatment `fetch_url_to_workspace` already had.
- **Internal exceptions** outside the body's own retry handling now surface as the standard `CRITICAL TOOL EXECUTION ERROR` string instead of propagating raw.

Pinned by `tests/test_web_search_quota_wrapper.py` (5 cases): AST guard that the decorator stack is exactly `@tool` over `@with_quota` (the `bugs/done/quota-exhaustion` precedent — a helper between them silently disables the quota path; guard proven to fail on the pre-fix source), AST guard that the manual `check_quota` is gone (double-charge), the loop-detector repro (RED before fix: second identical search returned results), distinct-queries-not-flagged, and exhausted-pool-returns-error-without-touching-the-provider (charge-once). Suite: 45 passed.

## Validation

**Live run 1: 2026-10-06, session `1d7b83ef` (fast_test) — wiring exercised, loop path NOT fired.** All 4 `web_search` calls ran through the new `@with_quota` stack: pool charged correctly (14 web calls total, no premature exhaustion, no double-charge), SEARCH BLOCKED fired at event 14 (ratio guard inside the body — proves the decorator change left the body intact), no raw exceptions, no false loop aborts on distinct queries. But all 4 queries were distinct, so `_check_repeat` never saw an identical consecutive pair — the loop-abort path for `web_search` remains unit-pinned only. Commit held until an organic identical-search loop fires (user decision 2026-10-06). Note the abort mechanism itself is live-proven in production via `fetch_url_to_workspace`, which has carried the same decorator throughout.

Also observed: the Orchestrator concluded with a direct "unable to find figures" text and never wrote `final_report.md`, so Phase 3 was not exercised — model behaviour under fast_test, not a gate defect.

Still pending: a live session that repeats a near-identical search must show the loop abort (turn salvage) instead of the provider being re-hit.

## Related

- `bugs/done/websearch-stall-no-return.md`, `backlog/dedup-fetches.md` — adjacent web-tool behaviours.
