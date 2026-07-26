# Supplementary/optional report sections carry confident unverified claims

**Status:** Open
**Found:** 2026-07-26, session `ecf57d30-5d23-4f71-9964-abc2b6b5470f`
**Severity:** Medium-High (wrong facts indistinguishable from sound ones in a shipped report)

## Symptom

The report's "Newer Models" section presented five entries with confident specifications. On post-hoc web verification:

- DeepSeek V4 (Pro 1.6T/49B, Flash 284B/13B) — REAL and accurately specced.
- PrismML Bonsai 27B (1-bit/ternary, Qwen3.6-based, July 2026) — REAL, substantially correct.
- Qwen3 family — real.
- "Mistral Large 2026, 123B parameters" — WRONG. Real flagship is Mistral Large 3, 675B MoE, Dec 2025.
- "Llama 4 8B/13B/27B, released August 2026" — WRONG. No such release; those sizes/date do not exist. Meta's 2026 release was Muse Spark (proprietary), not a Llama of those sizes.

So the section mixed accurate real models with confidently-stated wrong ones, with NOTHING in the report distinguishing which entries were well-sourced and which were not. A reader cannot tell the sound entries from the invented ones without external fact-checking.

## Why this is the real problem (generic, not section-specific)

The defect is NOT "the newer-models section is bad" and the fix must NOT special-case that section, that topic, or recency. The general failure is:

- Claims that are weakly-sourced, single-sourced, or unsourced are rendered with the SAME confident tone and formatting as well-corroborated claims, anywhere in the report.
- Optional/supplementary/discovery-style asks ("any newer models", "anything else relevant") invite the agent to fill the section rather than report "nothing found meeting the bar", so it emits plausible-looking entries.

A supplementary section that invents plausible entries is WORSE than omitting the section, because the errors are camouflaged among the correct entries.

## Fix direction (MUST be generic)

Applies to ANY claim in ANY section, not a named section or topic:

- Every factual entry carries its sourcing state, and unsourced/single-informal-source claims are visibly marked (e.g. "unverified") rather than stated as fact — the existing Data Integrity "mark unverified" rule should extend to supplementary/optional sections, which currently appear to escape it.
- For open-ended/discovery asks, "nothing found meeting the sourcing bar" is a valid and preferred answer over filling the section with plausible entries — mirror the Analyzer's existing empty-source terminal result, applied at synthesis for optional sections.
- No claim should be rendered at higher confidence than its weakest supporting source justifies, regardless of which section it sits in.

## Retest

Re-run the exact query below. In the resulting report, check the "newer models" / last-90-days portion (and every other section): is each entry either backed by a cited source or explicitly marked unverified? Are any entries stated as bare fact without sourcing? A pass = no confidently-stated unsourced claims anywhere; discovery sections either cite or say nothing found.

```
Produce a definitive guide to the largest and best local LLMs that can realistically run on a Beelink GTR9 Pro (Ryzen AI Max+ 395, Radeon 8060S, 128GB LPDDR5X unified memory) as of today. Search the web for benchmarks, GitHub issues, Reddit discussions, Hugging Face model cards, LM Studio compatibility reports, llama.cpp changes, and ROCm/Vulkan developments. Compare Qwen3-Next-80B, GPT-OSS-120B, DeepSeek-R1 Distill 70B, GLM-4.5 Air, Kimi K2, Gemma 3, Mistral Medium, and any newer models released in the last 90 days. For each model determine: whether it fits in memory, recommended GGUF quantisation, expected tokens/sec on Vulkan and ROCm, quality for software architecture planning, instruction following, long-context reliability, known issues on Strix Halo, and whether LM Studio or Ollama is currently the better runtime. Where sources disagree, explain why and identify the most credible evidence. Finish with a ranked recommendation for planning large software projects on this exact hardware.
```

## Evidence

- Session: `ecf57d30-5d23-4f71-9964-abc2b6b5470f`
- Verified via web search 2026-07-26: DeepSeek V4 real/accurate; PrismML Bonsai 27B real; Mistral "Large 2026/123B" wrong (real: Large 3 / 675B / Dec 2025); "Llama 4 8B/13B/27B Aug 2026" wrong (no such release; Meta 2026 = Muse Spark, proprietary)
- The section cited one backend-benchmark source for the whole block; per-entry model claims were uncited
