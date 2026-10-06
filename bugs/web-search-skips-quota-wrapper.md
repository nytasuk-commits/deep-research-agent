# web_search bypasses @with_quota, losing loop detection and the error wrapper

**Status:** Open
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

## Fix direction

Apply `@with_quota` to `web_search` and drop the manual `check_quota` call, or factor `_check_repeat` + error wrapper into the manual path. The ratio guard stays. Validate with a session that repeats near-identical searches.

## Related

- `bugs/done/websearch-stall-no-return.md`, `backlog/dedup-fetches.md` — adjacent web-tool behaviours.
