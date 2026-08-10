# Orchestrator collapses named entities into dimensional todos, defeating per-model budgeting

**Status:** Open
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
