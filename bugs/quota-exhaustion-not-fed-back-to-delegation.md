# Quota exhaustion not fed back to delegation; analysis delegated for unsaved source

**Status:** Open
**Found:** 2026-07-27, session `42140aa1-398b-42bc-b975-f059214e4d0c` (branch `review-gate-fixes`)
**Severity:** Medium-High — analysis tasks are delegated for source files that were never saved, producing "file not found" and silent loss of a named model from the report

## Symptom

The Orchestrator delegated an Analyzer task to read `mistral_hardware_requirements.md` (event 1227), but that file was never saved — its fetches had been rejected on quota. The Analyzer returned "file not found" (events 1230, 1234, 1238), and Mistral (an explicitly-named mandatory model) received no analysis and was effectively dropped.

## Root cause (confirmed from log)

Immediately before the Mistral delegation, the same context received an explicit quota-exhaustion result (event 1226): "Quota reached. You have used the 'web_calls' tool 21 times out of your limit. STOP CALLING TOOLS NOW ... Any further tool call is a failure." The fetches intended to save the Mistral file (events 1220, 1222) had already been quota-rejected (event 1221).

Context analysis: the quota rejection at event 1226 and the `delegate_tasks` at event 1227 are at the same context level — i.e. the agent that delegated the Mistral analysis had just received the "STOP" quota message one call earlier and delegated anyway. So this is NOT purely a missing feedback path — the stop signal was present in context and was ignored. `delegate_tasks` is itself a further tool call, which the quota message explicitly forbids.

The result is an analysis task spawned for a source file that does not exist in the workspace, wasting the delegation and silently dropping a mandatory model.

## Note on interaction with other bugs

This is downstream of, but distinct from, `bugs/orchestrator-collapses-named-entities-into-dimensional-todos.md`. That bug explains why Mistral was under-resourced (no per-model task/budget). This bug is about the delegation behaviour once a fetch has failed: the pipeline delegates analysis for an unsaved file rather than detecting the source is missing. Both contributed to Mistral being lost; fixing either reduces the damage, fixing both is more robust.

## Fix directions (all three logged; decision deferred)

1. **Delegate-time file-existence guard (mechanical, buildable now, no model judgement):** At `delegate_tasks`, before spawning an analysis task that references a workspace source file, verify the file exists in the workspace. If it does not, do not spawn the task; return that the source is missing so the Orchestrator can react (e.g. mark the model unretrievable rather than delegate blindly). This sidesteps both quota-signal-reading and instruction-following entirely. Candidate location: the `delegate_tasks` tool implementation.

2. **Orchestrator checks remaining quota before delegating (needs affordance):** Have the Orchestrator consult remaining web_calls budget when planning fetch/delegate steps, and avoid committing delegations it cannot resource. NOTE: it is not yet confirmed that remaining quota is queryable by the agent — if no such read affordance exists, this fix requires adding one first. Buildability unconfirmed.

3. **Feedback path / stop-signal enforcement:** Ensure fetch-failure and quota-exhaustion signals propagate to the delegating context AND are honoured. On this run the signal was present in context but ignored, so pure feedback is insufficient by itself; this direction would need enforcement (e.g. the run loop refusing further tool calls after a quota-stop, rather than relying on the model to comply). Overlaps the existing strengthened quota-exhaustion message work.

Decision on which direction(s) to implement is deferred.

## Evidence

- Session: `42140aa1-398b-42bc-b975-f059214e4d0c`
- Event 1221: fetch of Mistral URL quota-rejected
- Event 1226: explicit "Quota reached ... STOP CALLING TOOLS NOW ... Any further tool call is a failure" in the delegating context
- Event 1227: `delegate_tasks` for `mistral_hardware_requirements.md` issued anyway (a further tool call)
- Events 1230 / 1234 / 1238: Analyzer returns "file not found" for the unsaved source
- Also observed in the same not-found sub-agent: a `list_workspace_files` call returning "Requested function not found" (events 1231/1232) — the Analyzer reached for a tool it does not have; minor, logged here for context but not the subject of this bug

## Retest

Re-run the standard 7-model query. A pass = no analysis task is delegated for a source file absent from the workspace; when a fetch fails (quota, timeout, block), the affected model is either retried within budget or explicitly marked unretrievable in the report, rather than delegated blindly and silently dropped.

## Related

- `bugs/orchestrator-collapses-named-entities-into-dimensional-todos.md` (upstream cause of the under-resourcing)
- `delegate_tasks` tool implementation (candidate location for fix direction 1)
- Strengthened quota-exhaustion message (existing work; relevant to fix direction 3)
