# Orchestrator collapses named entities into dimensional todos, defeating per-model budgeting

**Status:** Closed - both fix-plan steps built, retest passed on session 8313dc8f
**Found:** 2026-07-27, session `42140aa1-398b-42bc-b975-f059214e4d0c` (branch `review-gate-fixes`)
**Severity:** High — a mandatory named model silently dropped from the report; per-model budget allocation rendered ineffective

## Symptom

On the standard 7-model query, Mistral Medium (an explicitly-named mandatory model) received no analysis in the run. The Analyzer delegated to read `mistral_hardware_requirements.md` returned "file not found" because the file was never saved — both fetch attempts for it were rejected on quota, one early (failed to save) and two at end-of-run (quota exhausted).

## Root cause (confirmed from log)

The Orchestrator's `write_todos` plan (event 3) decomposed the query **by research dimension**, not by named model. Every todo bundled all seven named models together, e.g.:

- "Research memory requirements for each model: Qwen3-Next-80B, GPT-OSS-120B, DeepSeek-R1 Distill 70B, GLM-4.5 Air, Kimi K2, Gemma 3, Mistral Medium"
- "Research Vulkan performance benchmarks for each model on Strix Halo"
- "Research ROCm performance benchmarks for each model"
- ...etc.

Not a single per-model todo was created. The first `delegate_tasks` call (event 6) mirrored this: 8 dimensional tasks, zero per-model tasks.

This directly violates the Orchestrator instruction at `src/prompts.py` line 62, which states: "If the query explicitly names specific entities to research or compare ... create ONE separate research todo per named entity — NEVER combine multiple named entities into a single todo."

The instruction is present and correct. The model disobeyed it.

## Why this is damaging

The per-task web_calls budget allocation (built and previously verified — e.g. Gemma capped at exactly its computed share, Kimi researched correctly with even coverage) operates on the unit of a delegated task. When all seven named models are collapsed into one "memory requirements" task, they share a single budget share and compete within it. A model scheduled late in that shared task (Mistral) can be squeezed out entirely. The budgeting machinery is intact but never gets per-model tasks to protect, so it cannot prevent starvation of an individual named model.

Consequence: per-model budgeting is effectively defeated whenever the Orchestrator plans by dimension. Coverage of named models becomes order-dependent and starvation-prone, exactly the failure the "one task per named entity" work was intended to eliminate.

## Evidence

- Session: `42140aa1-398b-42bc-b975-f059214e4d0c`
- Event 3 (`write_todos`): all todos dimensional, each listing all 7 models together
- Event 6 (`delegate_tasks`): 8 dimensional tasks, no per-model task
- Mistral trace: searched early (ev 24), one early fetch that did not save (ev 113 region), then no Mistral activity for ~2.5h, then quota-rejected fetches at end-of-run (ev 1220, 1222), then "not found" on the delegated analysis (ev 1230, 1234, 1238)
- Relevant instruction: `src/prompts.py` line 62 (present and correct; disobeyed)

## Fix plan (agreed order)

1. **Prompt strengthening first (prompt-only, low-risk):** reinforce the line 62 rule, most likely with a concrete worked example showing what a per-named-entity todo list looks like for a query naming N models, so the rule is not flattened into dimensional buckets. Test across several runs.
2. **Code enforcement (only if prompt strengthening does not hold after several runs):** at the planning boundary, detect when a query names multiple entities but the todo list collapses them into dimensional todos, and reject / re-prompt. Reliable but a real change in the planning path — deferred unless step 1 proves insufficient.

## Retest

Re-run the standard 7-model query and inspect the initial `write_todos` output: does it contain one separate research todo per named model (Qwen3-Next-80B, GPT-OSS-120B, DeepSeek-R1 Distill 70B, GLM-4.5 Air, Kimi K2, Gemma 3, Mistral Medium), rather than dimensional todos each listing all models? A pass = per-model todos created, and every named model receives at least one saved source and appears in the final report.

## Related

- `src/prompts.py` line 62 (one-task-per-named-entity instruction)
- Per-task web_calls budget allocation (built, previously verified)
- Backlog item 1 (funnel / stop-when-satisfied) and item 2 (rollover) — related budget-efficiency work, but this bug is upstream of both: no per-model task means no per-model budget to funnel or roll over

## Resolution (2026-08-10)

Both steps of the fix plan landed, and the retest specified above passes on the exact query and pass condition.

**Step 1 (prompt) - built.** `src/prompts.py` line 74 now carries the concrete worked example this file asked for: it instructs passing `named_entities`, states that named entities are mandatory deliverables rather than a priority buffet, restricts the drop-under-budget-pressure reasoning to supplementary research only, and ends with an explicit contrast - pass `named_entities=["Model A", "Model B", "Model C"]` with three separate todos, NOT a single todo bundling them.

**Step 2 (code enforcement) - also built,** by `d2a5620`, rather than being deferred as the plan anticipated. `src/tools/todos.py` validates the declared `named_entities` and returns early with "TODO list REJECTED - not written" in two cases: any named entity with no todo line of its own, and any single todo line containing two or more named entities. The second is precisely the dimensional collapse this bug describes, and the error text quotes the offending line back with the failure pattern named. The list is not persisted on rejection, so the Orchestrator cannot advance on a collapsed plan.

**Retest passed - session 8313dc8f (2026-08-10), the standard wide query.** The `write_todos` call at event 2 created ONE todo per named model - Qwen3-Next-80B, GPT-OSS-120B, DeepSeek-R1 Distill 70B, GLM-4.5 Air, Kimi K2, Gemma 3, Mistral Medium - with the research dimensions listed within each per-model todo. That is the inverse of the failure recorded here, where every todo was a dimension listing all seven models. All seven were declared in `named_entities`. Not one dimensional-bundle todo was produced.

**Second half of the pass condition also met.** Every named model appears in the final report, and Mistral Medium - the model silently dropped in `42140aa1` - has its own numbered section (#7) with a saved source (`mistral_medium_3_5_local_guide.md`), memory requirements, a quantisation recommendation and quality metrics. Where evidence was thin it said so rather than dropping the model or inventing a figure: its Vulkan throughput reads `~40 tok/s (estimated based on similar MoE models)`, marked Unverified, with an explicit note that no benchmark was found for that configuration.

**Known limitation, not blocking closure.** The code enforcement only engages when the agent actually passes `named_entities`; if the argument is omitted, the guard is skipped and the write proceeds unvalidated. The prompt says MUST, so that residual path depends on instruction-following - the same class of failure that caused this bug. It is not currently a problem in practice (the worked example is holding), but if a future run shows a collapsed plan, check first whether `named_entities` was passed at all before assuming the validator failed. Making the argument mandatory whenever the query names entities would close the gap, and would be the natural step 3.