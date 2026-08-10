# web_search module-level state: shared failure counter and orphaned search threads

**Status:** Open
**Type:** Backlog (two related defects)
**Priority:** Medium — the counter defect is confirmed reachable; neither causes a stall
**Source:** Identified during the `websearch-stall-no-return` root-cause read; split out 2026-08-08

Both defects are consequences of module-level state where per-task state is needed. Neither caused the stall that bug described, and neither is fixed.

## Defect 1: `_consecutive_search_failures` is shared across all agents

`src/tools/web.py` line 44. A single module-level counter accumulates failures from every concurrently-running agent, so one agent's failures can trip the 6-failure permanent `SEARCH SERVICE UNAVAILABLE` response on an unrelated agent's behalf. That response instructs the receiving agent not to retry or reword and to report search as unavailable — so an agent that has had no failures of its own can be told search is dead and stop researching its topic.

**Confirmed reachable.** While writing `tests/test_search_backoff.py` (2026-08-08) this was hit directly and traced: three successive failing searches in one process accumulate 6 failures across searches, and the third search returns `SEARCH SERVICE UNAVAILABLE` before reaching its own retry logic. The counter is only reset on a successful search or an explicit empty result (`3c0a0b3`), so under a partial provider outage the counter ratchets up globally while individual agents are still healthy.

Candidate fix: move the counter into the per-task quota context (`tool_quotas_ctx`), the same mechanism `_check_repeat` uses for per-task state, so each agent's failure history is its own. A genuinely provider-wide outage would then be signalled by every agent independently reaching its own threshold, which is the correct behaviour anyway.

## Defect 2: `asyncio.wait_for` does not cancel the underlying thread

`src/tools/web.py`, the `asyncio.wait_for(asyncio.to_thread(_do_search), timeout=45)` call. When the 45s ceiling fires, `wait_for` cancels the *await*, not the thread. The `_do_search` thread keeps running to completion, bounded only by the DDGS client's own `timeout=20` set in `get_ddgs_client()`. Under repeated timeouts this leaks threads for the life of the process and issues provider requests nobody is waiting for — which can itself contribute to rate-limiting, feeding the failure path in defect 1.

Candidate fix: no clean cancellation exists for `to_thread`. Options are to accept the leak and document it, to reduce the client-level timeout so the orphaned thread dies sooner than the outer ceiling, or to move the search onto a cancellable transport (an async HTTP client rather than a threaded sync one).

## Why these are backlog and not bugs

Neither produces an observed failure on its own. Defect 1 degrades research quality invisibly under provider trouble; defect 2 wastes threads and requests. Both are worth fixing when the search path is next touched, and defect 1 should be done first since it has confirmed reach and a clear fix.

## Related

- `bugs/done/websearch-stall-no-return.md` — the stall these were found alongside
- `3c0a0b3` — empty results reset the counter rather than incrementing it
- `tests/test_search_backoff.py` — where defect 1 was hit in practice
- `src/tools/core.py` — `tool_quotas_ctx`, the per-task state mechanism defect 1 should use
