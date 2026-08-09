# web_search stalls with no return, hanging the run

**Status:** Closed — fixed and unit-tested 2026-08-08
**Severity:** High — hangs an otherwise healthy run
**Root cause:** CONFIRMED — global `_backoff_lock` held across the retry sleep
in `src/tools/web.py` (lines 492–493)
**First observed:** session_fd50dfab (2026-08-03), branch `multi-endpoint-router`

## Symptom

The run stops progressing with both inference endpoints idle and showing ready.
No error, no timeout, no abort — the TUI simply stops producing events.

## Evidence

`session_fd50dfab-c246-4ce5-8451-277aa8b53de5.json`, 1148 events,
12:43:00 → 13:14:31 (~31 min before manual quit).

Final events:

| Event | Time | Source | Call |
|---|---|---|---|
| 1138–1142 | 13:14:28 | SubAgent_Local events calendar August 3- | five `function_result` arriving simultaneously |
| 1143 | 13:14:28 | same | `think_tool` |
| 1144 | 13:14:29 | same | result |
| 1145 | 13:14:30 | same | `web_search` |
| 1146 | 13:14:30 | same | `web_search` |
| 1147 | 13:14:31 | same | `web_search` |

Three `web_search` calls issued within ~1s, none returning a `function_result`.
Nothing follows. The two-minute gap before the batch of five results at 13:14:28
suggests the same agent was already backed up before the final three calls.

## What it is not

- Not the abort path. A forced test abort fired cleanly at 13:07 (event 979)
  and the run continued for seven more minutes afterwards.
- Not inference. Both endpoints were idle and healthy at stall time.
- Not the loop-breaker. One genuine force-terminate occurred at 13:08
  (event 1051) and was handled correctly.

## Root cause (confirmed by reading src/tools/web.py)

The original suspicion — that `web_search` lacks a timeout — is WRONG. Line 477
wraps the search in `asyncio.wait_for(asyncio.to_thread(_do_search), timeout=45)`.
The request path is bounded.

The stall is in the retry path. Lines 490–493:

```python
if attempt < max_attempts - 1:
    wait = 30 * (2 ** attempt)   # 30s, then 60s
    async with _backoff_lock:
        await asyncio.sleep(wait)
```

`_backoff_lock` is a module-level `asyncio.Lock` and the sleep happens INSIDE it.
Every concurrently-failing searcher therefore serialises: each must acquire the
lock, then sleep 30s or 60s while holding it, and the next agent's wait does not
begin until the previous one's has finished. The delays become additive across
agents instead of shared. The apparent intent — one agent's backoff pausing the
others rather than all of them hammering the provider — is not achieved by
holding the lock through the sleep.

The 45s ceiling covers `_do_search` only. Nothing bounds the backoff, so a single
`web_search` call can consume 3 x 45s plus 30s plus 60s of its own sleeps, plus
unbounded queue time proportional to how many other agents are also failing.
Every waiting agent holds its global semaphore permit and its router slot
throughout, so the pipeline drains into the lock queue and both endpoints go
idle.

### Session evidence supporting this

- 4 x `Search failed`, 1 x `SEARCH SERVICE UNAVAILABLE`, and ZERO 45-second
  timeout messages. The searches were erroring, not hanging — which routes
  straight into the backoff branch.
- The two-minute gap followed by five `function_result` events arriving
  simultaneously at 13:14:28 is agents being released from the lock queue in a
  batch.
- 6 calls were in flight and unanswered at stall time, one of them the
  Orchestrator's own `delegate_tasks`. The top-level call never returned, which
  is why nothing progressed at all.

## Secondary defects found in the same read

Both are consequences of module-level state where per-task state is needed.
Neither causes the stall; both are worth fixing alongside it.

1. `_consecutive_search_failures` is a module-level counter, so failures from
   unrelated agents accumulate together. One agent can trip the 6-failure
   permanent `SEARCH SERVICE UNAVAILABLE` message on another agent's behalf.
2. `asyncio.wait_for` cancels the await but not the underlying thread, so a
   timed-out `_do_search` keeps running. It is bounded only by the DDGS client's
   own `timeout=20` set in `get_ddgs_client()`.

## Next step

Decide the backoff model before editing. The sleep must not be held under a
shared lock. Two candidate shapes, not yet chosen:
- Release the lock before sleeping and use it only to guard a shared
  "next-allowed-search" timestamp, so agents share one backoff window rather
  than queueing behind each other's sleeps.
- Drop the cross-agent coordination entirely and let each agent back off
  independently, accepting more provider load.

## Related

- `backlog/fetch-ceiling-timeout-frequency.md` — fetch timeout not a hard ceiling
- Stall protection generally: the stream inactivity ceilings were reverted and
  must not be reintroduced via manual stream iteration

## Resolution (2026-08-08)

Fixed on branch `bug-triage`. `_backoff_lock` now guards only a shared `_next_allowed_search` deadline; the sleep happens outside the lock:

- The lock is acquired just long enough to read the current deadline, extend it by the wait, and store it back.
- `delay` is then computed against the deadline and awaited with the lock released.

Concurrently-failing agents therefore observe one common backoff window and resume together, rather than each sleeping in turn while holding the lock. The additive queueing is gone, and no agent holds the lock — or blocks another's progress — while waiting. Each still holds its own semaphore permit and router slot during its own wait, but that is bounded by the shared window rather than by the number of other failing agents.

**Unit-tested.** `tests/test_search_backoff.py` asserts `asyncio.sleep` is never called while `_backoff_lock` is held. It was verified as a real guard rather than a vacuous one: moving the sleep back inside the lock makes the test fail, and the test also asserts the backoff branch was actually reached, so it cannot pass silently if the search returns early. Suite is now 11 tests.

**Not reproduced live, and deliberately so.** The fix engages only when the provider returns genuine errors to concurrent agents, which cannot be forced on demand. Note also that `3c0a0b3` had already removed the specific trigger from `session_fd50dfab` — an empty result set was being treated as a provider failure, costing three attempts and 90s of serialised backoff per empty query. Empty results now return early as a valid zero-hit result. So the observed stall was already unreachable by that route; this change fixes the underlying defect, which rate-limiting or a provider outage could still have reached.

**Secondary defects split out.** The two module-level-state defects recorded above are NOT fixed and are tracked in `backlog/search-module-level-state.md`. Defect 1 (shared failure counter) was independently confirmed reachable while writing the unit test, where three successive failing searches tripped `SEARCH SERVICE UNAVAILABLE` across search boundaries.
