# Memory bandwidth figures unreconciled across report sections

**Status:** Closed — resolved as working-as-intended (session ecf57d30). Reconciliation confirmed firing: the Reviewer caught the three-way bandwidth conflict (256/215/273 GB/s) under checklist rule 1 and the Orchestrator acted on it in the correction step. The 273 GB/s figure originated as a factually-wrong value in one weaker source (specpicks Mistral review stated it as the Ryzen's spec; it is actually the Mac M4's) and was removed in correction. Outcome resolved to the specced 256 GB/s, accepted as correct (the manufacturer-specced-and-sold figure). Note: the measured ~215 GB/s figure WAS present in this run (contrary to the original report). No code or prompt change required.
**Found:** 2026-07-26, session `ecf57d30-5d23-4f71-9964-abc2b6b5470f`
**Severity:** Medium (silent factual inconsistency in a shipped report)
**Relates to:** backlog item 6 (Searcher consolidation flattens source conflicts); reconciliation rule committed but never confirmed firing

## Symptom

The final report states three different memory-bandwidth figures for the same hardware (Ryzen AI Max+ 395 / Strix Halo LPDDR5X) and never reconciles them:

- Hardware spec table: 256 GB/s (stated as fact)
- Mistral Medium section: ~273 GB/s (stated as fact, attributed to a source)
- Known real-world figure (operator knowledge, CURRENT_ISSUES.md): 212-215 GB/s

Two different figures are presented as fact in different sections of the same document. The real-world figure appears nowhere.

## Root cause (suspected, not confirmed)

The Analyzer/Searcher consolidation path merges or passes through differing figures without surfacing the conflict, so the Orchestrator never sees a disagreement to reconcile. The Data Integrity / cross-item consistency rules and the committed reconciliation rule did not fire on this metric. Same theme as backlog item 6: reconciliation is committed but has not been confirmed to fire in any run.

## Fix direction (MUST be generic, not metric-specific)

The fix must NOT special-case memory bandwidth, or any single metric or field. Bandwidth is only the example that surfaced here. The mechanism must apply to ANY quantity that appears more than once in the pipeline:

- Any physical/numeric quantity for the same entity+configuration that arrives with differing values from different sources must be preserved with per-value attribution through consolidation, rather than one value being silently chosen or averaged.
- Cross-section consistency must hold for ANY repeated quantity: the same quantity must not appear as two different "fact" values in different sections of one report.
- First confirm whether the committed reconciliation rule fires AT ALL on a clean run (it has never been observed firing) — the defect may be that the rule never triggers, not that this metric is special.

## Retest

Re-run the exact query below and inspect the report for any single quantity stated as two different fact-values across sections (and specifically whether Strix Halo memory bandwidth is now reconciled / attributed rather than stated as two bare facts):

```
Produce a definitive guide to the largest and best local LLMs that can realistically run on a Beelink GTR9 Pro (Ryzen AI Max+ 395, Radeon 8060S, 128GB LPDDR5X unified memory) as of today. Search the web for benchmarks, GitHub issues, Reddit discussions, Hugging Face model cards, LM Studio compatibility reports, llama.cpp changes, and ROCm/Vulkan developments. Compare Qwen3-Next-80B, GPT-OSS-120B, DeepSeek-R1 Distill 70B, GLM-4.5 Air, Kimi K2, Gemma 3, Mistral Medium, and any newer models released in the last 90 days. For each model determine: whether it fits in memory, recommended GGUF quantisation, expected tokens/sec on Vulkan and ROCm, quality for software architecture planning, instruction following, long-context reliability, known issues on Strix Halo, and whether LM Studio or Ollama is currently the better runtime. Where sources disagree, explain why and identify the most credible evidence. Finish with a ranked recommendation for planning large software projects on this exact hardware.
```

## Evidence

- Session: `ecf57d30-5d23-4f71-9964-abc2b6b5470f`
- Report locations: hardware spec table (256 GB/s), Mistral Medium section (~273 GB/s)
- Real-world value 212-215 GB/s absent from report
