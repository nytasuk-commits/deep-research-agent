# Fetch Timeout Not a Hard Ceiling

**Status:** Open
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
