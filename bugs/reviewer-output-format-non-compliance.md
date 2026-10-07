# Reviewer verdict does not meet its required output format

**Status:** Open — fix applied 2026-10-05 (prompt rewrite + code-side guard). Post-fix cohort 2026-10-06: 4 verdicts — 2/2 compliant under normal quotas (worked-example shape, guard silent), 2 prose under fast_test where the Reviewer exhausted the reduced read quota before reading the report; the guard flagged both, its first live firings. Still short of statistical validation; fast_test verdicts are quota artifacts, see Validation.
**Severity:** High — Phase 3's value is an independent, machine-parseable verdict; when the format never lands, the review gate is silently degraded every run
**Derived from:** `docs/reviews/2026-09-07/todo.md` item 1

## Symptom

The Reviewer is required to return EXACTLY one of two shapes:

- a **numbered list** of integrity violations, or
- the single verbatim line `REVIEW PASSED: no integrity violations found.`

Across the observed corpus it has "never been compliant across seven observed runs" — the verdict arrives as bullets, or as narrated prose, or (in at least one recorded session) as a leaked malformed tool-call block rather than a clean verdict. Because the Orchestrator reads the returned text as-is, a badly-formed verdict is consumed as if it were a good one: the review still "happens," but its output cannot be parsed as the contract promises, so downstream handling and the traceability the whole Phase 3 stage depends on quietly degrade.

## Evidence

A sweep of the session logs over all `delegate_tasks` calls with `agent_id == "Reviewer"` found **87 Reviewer verdicts**:

- **11 (13%) comply** — 2 are the verbatim `REVIEW PASSED` line, 9 are a genuine numbered list.
- **44 use bullets** (dash/asterisk list) instead of the required numbered list — the dominant failure shape.
- the remainder are narrated prose or a leaked tool-call / think block rather than a verdict at all.

This replaces the earlier hand count ("seven observed runs") with a measured figure. The same fact was recorded, without a dedicated file, in two places:
- `bugs/done/reviewer-overrides-fetched-sources.md` — residual note: "The Reviewer's output format still does not reliably match the required numbered list."
- `backlog/general-vs-specific-task-decomposition.md` — "Reviewer output format has never been compliant across seven observed runs (bulleted or narrated, never the numbered list the prompt requires)."

The two failure shapes have **different root causes** and were fixed differently.

## Root cause 1 — bullets instead of a numbered list (the dominant shape)

The model renders in bullets because the prompt invited it to:

1. The old `# Output Format` section was itself written as a bullet list, so the model mirrored the style it was told with.
2. "a numbered list" was a *label* with no *shape* — there was no concrete example of what a compliant item looked like, so "numbered" stayed abstract while "bullet" was the nearest visible model.
3. The model correctly references the numbered checklist rules (Rule 4, Rule 8, …) but has no anchor for *how to render* its own list.

This is prompt-fixable. It is NOT fixed by adding prose to the Role section — `session_5091cd9a` (recorded in `bugs/done/reviewer-overrides-fetched-sources.md`) shows a large prose block degrading output format and being ignored outright. The fix is deliberately placed inside the existing numbered checklist, kept small.

## Root cause 2 — a leaked tool-call / think block (not prompt-fixable)

In at least one session the Reviewer's "verdict" is actually a malformed tool-call block (a `think_tool` reflection leaking out as text instead of a clean numbered list or the pass line). No prompt wording changes what the model *emits in that state* — the failure is in the stream/serialisation, the same tool-call malformation family documented against the Qwen-template-plus-LM-Studio issue. What the stack can do is **surface the non-conformance** rather than silently consuming a verdict that is not one, so both the consuming Orchestrator and the session log see the failure instead of it quietly degrading.

## Fix applied (2026-10-05)

### Root cause 1 — `src/prompts.py:375-382`

`# Output Format` rewritten to be explicit and example-anchored, with no Role-section prose added:

- "Your final message must be EXACTLY one of the two shapes below — and nothing else (no preamble, no headings, no summary, and no bullets or dashes)." → targets the prose/narration cases and forbids bullets outright.
- A concrete worked example (`1. Rule 4 (Sourcing): "59–62 tokens/sec" in the Executive Summary — …`) is the highest-leverage format anchor: it preserves the model's existing rule-naming habit while showing the exact rendering.

### Root cause 2 — code-side guard in `src/engine/orchestrator.py`

A pure classifier `_reviewer_verdict_issue(final_text)` returns a human-readable reason a verdict violates the contract, or `None` if it conforms:

- conforming = starts with `REVIEW PASSED`, OR starts with `1.` AND has no line-leading `-`/`*` bullets;
- non-conforming reasons distinguish a **leaked tool-call / think block** (root cause 2) from **bullets** vs a numbered list, from **narrated prose**, from an **empty** verdict.

At the Reviewer result-production site, when `agent_id == "Reviewer"` and the classifier flags an issue, a `⚠ The Reviewer's verdict does not meet the required output contract: <reason>` header is prepended to the result (the findings below are passed through unchanged). Gating strictly on `agent_id == "Reviewer"` — not on a task-name substring — avoids the false positives seen when sweeping (the "Analyze … review" Analyzer tasks). This is a **flag, not a rewrite**: safer than auto-renumbering, and it directly answers the bug's "silently degraded" complaint.

Pinned by `tests/test_reviewer_verdict_guard.py` (8 cases) so any future edit that loosens or tightens the conformance rules fails loudly.

## Validation

### First live run: 2026-10-06, session `59f439fd` — PASSED (n=1)

GPU-comparison prompt (three cards, prices + tokens/sec, declared winner). The verdict came back fully compliant in the worked-example shape:

- Seven numbered items, each naming the rule, the exact quoted text, and a one-line problem — e.g. `1. Rule 3 (Like-for-like): The reference configuration is stated as "128-bit memory bus / 16GB VRAM" but the RTX 3060 winner has only 12GB VRAM...`, then six Rule 9 dating items.
- Starts with `1.`, no line-leading bullets → guard returned `None`, no `⚠` header (correctly silent).
- Downstream handling also worked: the Orchestrator consumed the verdict, edited `final_report.md` in place, and every flagged figure gained a bracketed date marker.

n=1 is encouraging, not conclusive. Keep the bug open until the compliant share moves over a larger post-fix cohort.

### Guard fired live for the first time: 2026-10-06, session `c57d2d55`

Under fast_test, both review rounds in that session produced prose verdicts — the Reviewer exhausted the reduced `read_workspace_file` quota (15) on source-file checks before reading the report, and returned a quota-explanation instead of a verdict. The guard prepended the `⚠ ... does not meet the required output contract` header on both, exactly as designed: non-conformance surfaced, findings passed through.

Cohort read with this: **2/2 compliant under normal quotas; 0/2 under fast_test, both quota-induced.** The fast_test failures are an artifact of the profile (read limit 15 is too tight for the Reviewer's report+sources pass), not evidence against the prompt rewrite — but they are the guard's proof of firing. If fast_test stays in regular use, consider raising its `read_workspace_file` override or exempting the Reviewer.

### Sweep tool and corrected baseline

`tools/reviewer_verdict_sweep.py` reproduces the sweep with the guard's exact classifier (`^\s*1[\.)\s]` + bullet check) applied to the verdict **after stripping the `## Result for ...` wrapper** the engine adds — reading the raw session result without stripping it misclassifies every verdict as prose. Run `python tools/reviewer_verdict_sweep.py --since 2026-10-05` for the post-fix cohort.

Corrected baseline over `sessions/` only (2026-07-25..2026-08-28): **66 verdicts, 4 compliant (6%)** — 37 bullets, 25 prose/other, 2 numbered, 2 pass-line. This differs from the 87/13% figure above, which swept a wider corpus; the 6%/66 figure is the one the sweep tool reproduces. Note the corpus is dominated by four re-run validation prompt families (13/9/8/7 sessions), so before/after comparisons should re-run those same families rather than new queries.

## Related

- `bugs/done/reviewer-overrides-fetched-sources.md` — the opposite correctness failure (closed); carries the `session_5091cd9a` "keep the fix small, put it in the numbered checklist" caveat that shaped the root-cause-1 fix.
- `backlog/general-vs-specific-task-decomposition.md` — the other place the non-compliance was recorded.
- `bugs/delegate-tasks-accepts-string-not-list.md` (todo item 2) — the separate, related tool-call malformation family.
