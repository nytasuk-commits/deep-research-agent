# Restore Direct-Answer Fast Path for Simple Known Facts

**Status:** Open
**Type:** Backlog
**Source:** Design discussion; original upstream agent could answer trivially (e.g. "capital of France?" → "Paris") without delegation, a capability lost when the Orchestrator was tuned heavily toward research + report writing.

## Summary
The Orchestrator should be able to answer very simple, well-known, non-time-sensitive factual questions directly from the model's own knowledge, without spawning the research/delegation/report pipeline.

## Detail
Enhancements pushed the agent strongly toward "always plan → delegate → research → write report," which is correct for deep research but removed the fast conversational path for trivial questions. A direct answer is appropriate only when the fact is (a) simple, (b) well-known, and (c) non-time-sensitive — i.e. unlikely to have changed since the model's training (capitals, historical dates, definitions, settled science). Anything time-sensitive (prices, current office-holders, latest versions, anything described as "current"/"latest") or uncertain must still go down the research path.

Hard guardrail: Never invent information. The model's own sense of "I know this" is unreliable, so the routing must be conservative — when there is any doubt about whether a fact is known and stable, route to research rather than answering directly. Over-routing a few trivial questions to search is acceptable; confabulating one answer is not.

## Suspected fix
Add a pre-Orchestrator routing step or modify the "ASSESS COMPLEXITY" logic in ORCHESTRATOR_INSTRUCTIONS to include:
1. A fast-path check for simple factual queries
2. Criteria: simplicity, known stability, non-time-sensitivity
3. Conservative triage: when in doubt, route to research

## Related
- src/prompts.py ORCHESTRATOR_INSTRUCTIONS (the "ASSESS COMPLEXITY" step is the natural home for this triage)
- Bug: simple-query-tool-call-malform (that bug stands independently — malformed tool calls are wrong regardless of routing)
