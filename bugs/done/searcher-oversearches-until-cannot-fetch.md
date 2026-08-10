# Searcher over-searches until it cannot afford to fetch what it found

**Status:** Closed - mechanical guard built (a992607), retest passed on session 8313dc8f
**Found:** 2026-07-27, session `f365b0da-9707-4142-8b3e-02196d4e7e8e` (branch `todo-entity-enforcement`)
**Severity:** High — a mandatory named model (Qwen3-Next-80B) received no saved source and appears in the report only as "research incomplete due to quota exhaustion", despite the correct source having been found

## Symptom

Qwen3-Next-80B (an explicitly-named mandatory model) ended the run with no saved source file and a near-empty report section stating "Research incomplete due to quota exhaustion; memory requirements not confirmed." This is NOT the per-model-todo bug (that is fixed — the todo-entity-enforcement change worked, and Qwen3-Next had its own dedicated todo and its own budget on this run).

## Root cause (confirmed from log)

The Searcher task for Qwen3-Next spent its entire per-task web_calls budget on SEARCHES and had nothing left to FETCH with:

- ~20 `web_search` calls were issued for Qwen3-Next (events 11–128), many near-identical, repeatedly refining the query wording.
- Several returned usable results. Event 43 returned 5 results including the model's pages; event 63 returned 5 results including the exact target `Qwen_Qwen3-Next-80B-A3B-Instruct-GGUF` Hugging Face card — the source containing the memory/quantisation data the report later reported as missing.
- After finding the target, the Searcher issued ~10 MORE searches (events 70, 76, 82, 88, 95, 103, 110, 116, 122, 128) instead of fetching the card it had already located.
- The first fetch attempt (event 136) was quota-rejected: "Quota reached ... STOP CALLING TOOLS NOW." All subsequent fetches (events 136–166, ~13 attempts) were also rejected.

So the source was found and never fetched, purely because the task exhausted its budget searching. This is a failure of the funnel (discover → rank → fetch-best), the per-topic stop-when-satisfied instruction, and the spending rule ("never spend a call you cannot act on; never spend the last call on a search"). Those rules are committed (commit `e07e5d0`) but did not bite for this task on this run — the Searcher kept searching long after it had a fetchable result, and spent its last calls on searches rather than reserving budget to fetch.

## Why this matters

Per-model budget allocation (fixed) and per-model todos (fixed) guarantee each named model has a funded task. They do NOT guarantee that task spends its budget usefully. If the Searcher blows the allocation on redundant searches, a funded, correctly-scoped task still yields zero saved sources — and the model is silently reduced to a "not found" section even though the data was located.

## Fix direction (to design)

The funnel/spending-rule prompt work already exists but is not constraining behaviour here. Investigation needed before an edit:

- Confirm whether the Searcher prompt's funnel/stop-when-satisfied/spending-rule steps are reaching this task's context and are positioned at the decision point (i.e. at the moment of choosing search-again vs fetch), rather than only stated as general rules.
- Consider a mechanical guard analogous to the todo-entity-enforcement fix: e.g. once a task has issued N searches with at least one fetchable result returned, block further searches until at least one fetch has been made; and/or reserve a portion of each task's budget that can only be spent on fetches (never on searches), so a task can always act on what it found.
- The near-identical repeated queries (20 searches, many reworded variants) also suggest the loop/no-progress problem: the Searcher rephrases rather than fetching. A no-progress detector (N searches, no new fetch) may be relevant.

Decision on prompt-strengthening vs mechanical guard is deferred, but note: the funnel is already a committed prompt rule that did not hold, so — as with the todo bug — a mechanical guard is the more reliable route if prompt reinforcement does not bite after testing.

## Retest

Re-run the standard 7-model query. A pass = every named model that has a fetchable source found in search results ends the run with at least one saved source and a populated report section; no task exhausts its budget on searches while leaving a found-but-unfetched target. Specifically check Qwen3-Next-80B ends with a saved source and real memory/quant data rather than "research incomplete".

## Evidence

- Session: `f365b0da-9707-4142-8b3e-02196d4e7e8e`
- ~20 Qwen3-Next `web_search` calls (events 11–128); target GGUF card found by event 63
- First fetch attempt event 136, quota-rejected ("19/20 web_calls used"); ~13 fetch attempts all rejected
- Report section for Qwen3-Next-80B: "Research incomplete due to quota exhaustion"

## Related

- Searcher funnel / stop-when-satisfied / spending rule (commit `e07e5d0`; present but did not bite on this run)
- Backlog item 1 (funnel/spending) and item 2 (rollover)
- `bugs/quota-exhaustion-not-fed-back-to-delegation.md` (sibling: also a quota-exhaustion consequence, different mechanism)
- `bugs/orchestrator-collapses-named-entities-into-dimensional-todos.md` (fixed; this bug is the next link in the same coverage chain)

## Resolution (2026-08-10)

Fixed by the mechanical guard route this file identified as the more reliable option, and the retest passes on the exact model named.

**What was built.** Commit `a992607` added a search-to-fetch ratio guard in `src/tools/web.py` (guard at the search entry point, counter reset in the fetch path). A task may run at most `floor(task_quota / 6)` searches since its last fetch ATTEMPT; beyond that, `web_search` returns SEARCH BLOCKED naming the count and the ceiling, and instructing the agent to fetch what it already has. The divisor reflects a research unit of roughly one search plus up to five fetches. It was committed directly after `8d47247`, which is this bug being logged.

**Deadlock-free by design,** which the fix direction above specifically warned about. The counter resets on any fetch *attempt*, success or failure, so a task whose fetches are all rejected or blocked is never trapped without a way forward. `max(1, ...)` guarantees at least one search is always permitted regardless of how small the task quota is. The whole block is wrapped in try/except so a fault in the guard cannot break search, and the pre-existing capacity/reserve check still owns the low-budget case, so this guard only fires while fetch budget remains.

**Retest passed - session 8313dc8f (2026-08-10), the standard wide query.** Qwen3-Next-80B, which in `f365b0da` ended with no saved source and a section reading "Research incomplete due to quota exhaustion", ended this run with 18 saved sources. They include the GGUF cards that are the exact class of target previously found-but-never-fetched (`bartowski_qwen3_next_80b_gguf_instruct`, `bartowski_qwen3_next_80b_gguf_thinking`), plus the HF model cards, the llama.cpp quantisation docs, LM Studio and Ollama pages, and the arXiv technical report. Its report section carries real data: IQ4_XS at ~62 GB VRAM, a recommended quantisation, and a dated benchmark table. The phrase "research incomplete" and any quota-exhaustion language are absent from the report entirely.

Run-wide the ratio inverted: 114 fetches to 57 searches, against ~20 searches producing zero fetches for a single model in the failing run.

**Limits of this evidence.** The session log renders sub-agent calls flat, so search/fetch interleaving cannot be attributed to individual tasks - the longest consecutive-search run in the log is 8, which is the eight per-model tasks launching at once rather than one task over-searching. Per-task attribution would need the tree-grouped logging noted elsewhere as a separate feature. What is directly evidenced is the outcome the retest asks for: the previously starved model ends with saved sources and a populated section.

**Residual, not blocking closure.** The guard bounds searches per fetch attempt, not total searches across a task. A task alternating one fetch with `ceiling` searches could still spend heavily on searching - but never while holding unfetched results, which is the failure this bug describes. Budget efficiency in the wider sense remains backlog item 1 (funnel) and item 2 (rollover).
