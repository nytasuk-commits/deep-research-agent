# Supplementary/optional report sections carry confident unverified claims

**Status:** Closed — retest passed on session 8313dc8f (2026-08-08)
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

## Retest result (2026-08-08) — PASS

The retest query above was re-run as session `8313dc8f` (8 entities, 746 tool calls, 45878-char report). The discovery section was read in full from the final report. It passes on every criterion this file set.

**Per-entry sourcing is now present.** All six entries in "Newer Models Released in Last 90 Days" carry their own attribution — five cite PromptQuorum, one cites the LLM Gateway Timeline — addressing the original defect, where one backend-benchmark source was cited for the whole block while the per-model claims were uncited.

**Inferred figures are visibly marked.** Every performance estimate reads, e.g., `**Estimated Performance:** ~50 tok/s on Vulkan (based on similar MoE models) - *Unverified*`. That satisfies the requirement that no claim be rendered at higher confidence than its weakest supporting source justifies, applied uniformly rather than to a named section.

**Gaps are reported as gaps.** Kimi K2.7 Code lists `**Parameters:** Not specified` rather than inventing a figure, and the runtime section states that no direct head-to-head benchmarks were found for this hardware instead of filling the space. That is the "nothing found meeting the bar is a valid answer" behaviour this file asked for.

Nothing in the report matches the original failure pattern — `"Mistral Large 2026, 123B parameters"` and `"Llama 4 8B/13B/27B, released August 2026"` were stated with no sourcing and no unverified marker. A reader can now tell sourced entries from inferred ones without external fact-checking, which was the stated pass condition.

Credited to `4f03598` (forbid inventing entries in discovery sections at synthesis; Reviewer rule 7 flags unsourced discovery entries), which postdates this bug and implements the second and third bullets of the fix direction above.

**Caveat — what this does NOT establish.** The entries are *sourced*, not *verified*. The dominant source is PromptQuorum, an aggregator falling under the existing low-trust source tier (`7b19125`). Whether Qwen3.6 27B, Gemma 4 26B-A4B or Laguna XS 2.1 genuinely exist as described was not checked, and is a separate question from the one this bug raised. This bug was about sourcing state being invisible; that is fixed.

Also noted: this is the same session in which the Reviewer died while delivering its verdict (`bugs/reviewer-dies-delivering-verdict-on-long-report.md`), and "unsourced entries in the discovery section" was among the findings lost. The discovery section passes anyway, which indicates the synthesis-stage guidance in `4f03598` is doing the work rather than the review stage catching it afterwards — a stronger result, since it does not depend on the Reviewer surviving.
