# Rollover: unused per-task budget cannot reach capped tasks

**Status:** Open
**Type:** Backlog (correctness, not just efficiency)
**Priority:** High - promoted from `bugs/web-call-quota-exhausted-on-multi-entity-queries.md` after that bug's root cause was corrected
**Source:** Session 8313dc8f (2026-08-08), 8 named entities plus a discovery section
**Spec:** Step C of `function_specs/budget_allocation_spec.md`

## Problem

Per-task `web_calls` allocation is a hard partition. A task that finishes early leaves its remaining share unspent, and a task that exhausts its own share is cut off even though budget is sitting idle elsewhere in the same run.

Measured on session 8313dc8f:

- Effective budget: 240 calls (limit 250 minus 10 reserve).
- Actually spent: **171 calls**. 69 calls, about 29% of the budget, went unused.
- Three mandatory named entities were nonetheless cut off at their individual per-task caps: Mistral Medium at 21, Gemma 3 at 23, Kimi K2 at 24.

Those three caps are exactly their computed weighted shares, so allocation worked as designed. The failure is that nothing lets a capped task draw on the 69 unspent calls.

## Why this is a correctness issue, not only efficiency

Kimi K2 was cut off and its report figure was wrong: ~5.3 GB at Q5_K_M for a 1T-parameter model. Its Analyzer then spent 43 tool calls over 855 seconds working the partial material it already had. Budget that would have let its Searcher fetch a real source was available and unreachable. So the missing redistribution converted an affordable correct answer into an unaffordable wrong one - which is why this is promoted above "adds efficiency, not correctness" as the spec originally framed Step C.

## What was ruled out first

Three other explanations were tested against the session log and rejected. Recording them so they are not re-investigated:

- **Global pool exhaustion.** Never happened. The run spent 171 of 240. The original bug report attributed the caps to the global limit; the quota message prints the task's own limit, not the global one, so 21/23/24 are per-task shares.
- **Allocation shape / `flatness_constant`.** The weighting `W_i = (N - i) + flatness_constant` gives the first task 32 calls and the tenth 15, a 2.1x spread. Flattening it only redistributes the same total and would have given each entity about 24 - precisely what Kimi K2 had when it produced the wrong figure. Flattening cannot fix an unreachable surplus.
- **Insufficient total budget / feasibility gate.** There was no shortfall. 240 was ample for this query; 69 calls were left over. A launch-time capacity warning would have reported everything as fine and would have been correct to.

Also worth noting: the ordering the weighting relies on carries no priority information for named entities. In this run the todo order and the `named_entities` order were identical to the order the models happened to appear in the user's query sentence. Mistral Medium received the smallest mandatory share because it was typed last.

## Design requirement

Reserve-on-start / release-on-complete with three-state tracking, per Step C of the spec. A task's share is reserved when it starts and released back to a shared surplus when it completes under budget; a task approaching its cap can draw from that surplus rather than being refused.

Constraints to respect:

- The run-level `reserve` (10 calls held for post-review fixes) is separate and worked correctly in this run. Rollover must not consume it.
- Allocation is computed inside `delegate_tasks` per call, reading `web_calls.limit` fresh from config each time. Any surplus pool must be run-scoped, not per-call, or a late single-task delegation will recompute against the full config budget as though nothing had been spent.
- `_run_single_task` seeds the per-task quota context; that is where a draw-from-surplus check would sit.

## Cheaper partial alternative to consider first

`backlog/dont-charge-quota-for-rejected-fetches.md` addresses the same shortfall from the other end: a fetch rejected as junk, blocked or too short still consumes a call from the task's share. Not charging for those recovers budget within the existing partition and needs no surplus-pool machinery. It will not fully substitute for rollover - a task can exhaust its share on entirely successful calls - but it is smaller, and worth measuring first to see how much of the gap it closes.

## Related

- `bugs/done/web-call-quota-exhausted-on-multi-entity-queries.md` - the bug this was promoted from, with its corrected diagnosis
- `backlog/dont-charge-quota-for-rejected-fetches.md` - the cheaper partial alternative above
- `function_specs/budget_allocation_spec.md` Step C (rollover) and Step D (feasibility gate)
- `bugs/done/searcher-oversearches-until-cannot-fetch.md` - the ratio guard stops a task wasting its share on searches; rollover is the complementary problem of a share being too small in the first place
