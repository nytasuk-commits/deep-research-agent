# Fetch Timeout Not a Hard Ceiling

**Status:** Closed - verified in code 2026-08-10; caller-side hang fixed
**Type:** Bug
**Source:** Spec item 5

## Summary
A fetch ran ~333s against a 30s httpx timeout (probable byte-trickle resetting it).

## Detail
The httpx timeout appears to be getting reset by intermittent data delivery (byte-trickle), allowing connections to run much longer than the configured timeout. This defeats the purpose of having a timeout ceiling and can cause runs to hang unexpectedly.

## Suspected fix
Implement a hard ceiling on fetch operations that isn't affected by intermittent data delivery. This may require:
1. Using a different timeout configuration
2. Implementing an absolute deadline check
3. Adding connection idle timeouts separate from read timeouts

## Progress

**Fix committed 2026-07-20 (commit a958662):** `_FETCH_HARD_CEILING = 60` in src/tools/web.py wraps the `asyncio.to_thread(_fetch)` call in `asyncio.wait_for`, giving a hard wall-clock ceiling on the entire fetch that httpx's resettable per-operation read timeout cannot defeat. On timeout, returns a "FETCH TIMEOUT" guidance message instead of hanging. Caps both byte-trickle and any runaway retry regardless of cause. Verified by inspection; NOT yet observed firing on a live run.

## Related
- Spec item 5

## Resolution (2026-08-10)

The reported symptom is fixed. Verified present and correctly placed in `src/tools/web.py` on branch `bug-triage`:

- `_FETCH_HARD_CEILING = 60` at line 58.
- Line 294 wraps the fetch in `asyncio.wait_for(asyncio.to_thread(_fetch), timeout=_FETCH_HARD_CEILING)`, so the ceiling is wall-clock on the whole operation and cannot be reset by trickling bytes the way httpx's per-operation read timeout can.
- Line 296 returns a FETCH TIMEOUT guidance message naming the limit and telling the agent nothing was saved and to try a different source, rather than hanging.

That closes the 333s-against-a-30s-timeout hang: whatever the server does, the caller is released at 60 seconds with an actionable result.

**Known residual, tracked elsewhere.** `asyncio.wait_for` cancels the await, not the underlying thread, so a trickling server still holds a `_fetch` thread after the ceiling fires, bounded only by httpx's own timeouts. This is the same mechanism as defect 2 in `backlog/search-module-level-state.md`, which covers the identical pattern on the search path (`wait_for` around `to_thread(_do_search)`). It is recorded there rather than duplicated here. It does not reintroduce the hang, because nothing waits on the orphaned thread; the cost is a leaked thread and a request nobody reads.

**No live firing observed, and closed anyway.** Session 8313dc8f made 114 fetches with no FETCH TIMEOUT in the log, which is equally consistent with the ceiling working and with no trickling server being encountered. Observing it fire requires a slow server to appear organically and cannot be forced, so this is closed on inspection - the same basis as `bugs/done/junk-fetches-saved-as-sources.md`. The code path is three lines and unconditional.
