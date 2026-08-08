# Global web_calls quota exhausts partway through multi-entity queries

**Status:** Open
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
