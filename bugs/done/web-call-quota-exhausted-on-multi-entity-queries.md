# Global web_calls quota exhausts partway through multi-entity queries

**Status:** Closed - root cause corrected, promoted to backlog/budget-rollover-unused-allocation.md
**Observed:** session_8313dc8f-fa04-4351-8e71-1b844d8592a1 (2026-08-08), 8 named entities plus an open discovery section

## Symptom
Three research subagents hit the global web_calls limit (250, with 10 reserved for post-review fixes) and were told to stop:
- SubAgent_Research Mistral Medium at 09:07:39 (21 calls used by that agent)
- SubAgent_Research Gemma 3 at 09:10:45 (23 calls)
- SubAgent_Research Kimi K2 at 09:21:14 (24 calls)

## Consequence
Those three entities were researched on partial evidence. Kimi K2 was worst affected: after its searcher was cut off, its Analyzer ran 43 tool calls over 855 seconds working the material it already had, and the resulting report contained an implausible Kimi K2 memory figure (~5.3 GB at Q5_K_M for a 1T-parameter model). Entities researched earlier in the run got a full budget; entities researched later got whatever was left.

## Root cause (candidate)
web_calls is a single global pool shared by all agents (config.yaml comment states quotas are GLOBAL). There is no per-entity allocation, so early entities can consume budget that mandatory later entities need. Ordering therefore determines research quality, which defeats the one-todo-per-named-entity guarantee: every named entity is a mandatory deliverable, but the budget is first-come-first-served.

## Notes
- Total run: 58 minutes, 746 tool calls, 45 subagents.
- This interacts with the existing backlog item on budget allocation and rollover.
- The reserve mechanism (10 calls held back for post-review fixes) worked as designed and is not implicated.

## Next step
Decide whether web_calls should be allocated per mandatory named entity rather than drawn from one global pool.

## Correction and resolution (2026-08-10)

The root cause recorded above is wrong on the central point, and the corrected finding has been promoted to `backlog/budget-rollover-unused-allocation.md`.

**The three agents did not hit the global limit.** The quota-exhaustion message prints the calling task's own `limit`, not the global pool's, so 21, 23 and 24 are those tasks' per-task allocated shares rather than calls consumed. They match the weighted allocation formula exactly: for the 10-task first delegation, with `flatness_constant: 7` against a 240 budget, the computed shares are 32, 30, 28, 26, 24, 23, 21, 19, 17, 15 - and Kimi K2 was index 4 (24), Gemma 3 index 5 (23), Mistral Medium index 6 (21).

**The global pool was never close to exhausted.** The run issued 171 web_calls against 240 available, leaving 69 unspent - about 29% of the budget idle while three mandatory entities were being cut off. So "early entities can consume budget that mandatory later entities need" did not occur; nothing was drained by anyone.

**Therefore the defect is the absence of rollover,** not a shared pool, not the allocation shape, and not a capacity shortfall. Per-task allocation is a hard partition with no path from unspent surplus to a capped task. See the backlog item for the measured evidence, the three alternatives ruled out, and the design constraints.

One incidental observation from the same log, not investigated: one `delegate_tasks` call passed `tasks` as a 1052-character string rather than a list. If `N` is taken as `len(tasks)` that would make the allocation arithmetic meaningless for that call. Worth a separate look.
