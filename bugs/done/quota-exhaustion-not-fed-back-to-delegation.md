# Quota exhaustion not fed back to delegation; analysis delegated for unsaved source

**Status:** Closed — fix direction 1 built and validated 2026-08-10
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

## Resolution (2026-08-10)

Fix direction 1 (delegate-time file-existence guard) is built, on branch `bug-triage`. Directions 2 and 3 remain unbuilt — see below for why direction 1 was chosen over them.

**What was added.** A `_resolve_source_files` helper in `src/engine/orchestrator.py`, called inside the `delegate_tasks` task loop before each coroutine is created. It extracts every `.md` filename named in the task instructions and checks them against `get_workspace_files()`. A named file that is absent has two possible causes, and conflating them would be a new bug:

- **The delegating agent garbled a filename that IS present.** Repaired in place: a case-only difference, or a single `difflib` match above a 0.85 cutoff, is substituted into the instruction and the task runs normally. Requiring exactly one candidate above a strict cutoff means an ambiguous guess is never silently applied. This matters because `b97a959` and the "Do NOT invent, shorten, or rename it" wording in the fetch result exist precisely because agents were mangling filenames — refusing those would throw away a source that is sitting in the workspace.
- **The fetch never saved the file.** The task is not spawned. If every task in the batch is skipped, `delegate_tasks` returns a refusal naming the missing files and instructing the caller to re-fetch or mark the item unretrievable, with no invented figures. If only some are skipped, a "Tasks not run" section is appended to `final_output` before the join, so a partial skip still reaches the parent rather than disappearing.

**Validated on session 54d461f3 (2026-08-10).** 45 tool calls, 4 delegations, 4 fetches all saved. Two research delegations named no file (helper no-ops), three named `beelink_gtr9_pro_official.md`, `minisforum_ms_a2_official_specs.md` and `final_report.md`, all present. Every task spawned; no refusal or skip anywhere in the log. Delegated filenames matched the `SAVED_FILENAME` confirmations exactly, including the quoted form `'beelink_gtr9_pro_official.md'`. That confirms no false refusals on the normal path.

**Not yet observed firing.** The guard's positive case needs a run in which a fetch genuinely fails, which cannot be forced on demand. The negative case — that it does not block healthy delegations — is confirmed.

**Near-miss worth recording.** The helper was first inserted between the `@tool` / `@with_quota` decorators and `async def delegate_tasks`, so both decorators bound to the helper instead: the guard was registered as the LLM-callable tool named "delegate_tasks", and real delegation lost its quota wrapper. `ast.parse` succeeded and the full test suite passed in that broken state, because no test exercises the delegation path. Caught by inspection and fixed by moving the helper above the decorators. Any future insertion near a decorated function should be checked with an AST walk of `decorator_list`, not a parse and a green suite.

**Why not directions 2 and 3.** Direction 3 (feedback path / stop-signal enforcement) is not sufficient on its own, and this bug's own evidence is why: the quota-stop message was present in the delegating context one call earlier and the agent delegated anyway. Enforcing it would mean the run loop refusing tool calls after a quota-stop, which is a larger change in the abort-sensitive region. Direction 2 (Orchestrator consults remaining budget before delegating) still rests on the unconfirmed premise that remaining quota is readable by the agent; that read affordance has not been verified to exist. Direction 1 needed no model judgement and no new affordance, which is why it was built first. Either of the others would still add value on top.

**Side-note from the Evidence section, now resolved.** The `list_workspace_files` call that returned "Requested function not found" (events 1231/1232) was the Analyzer reaching for a tool it did not have. `8b6ce76` subsequently granted that tool, so that specific error should not recur.
