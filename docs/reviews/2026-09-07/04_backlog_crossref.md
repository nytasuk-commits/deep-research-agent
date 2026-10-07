# Pass 4 — Backlog/Bug Cross-Reference (2026-09-07)

Scope: CURRENT_ISSUES.md, backlog/done/multi-endpoint-router.md, and every file in bugs/ and backlog/ including done/. Each item checked against current code state; all line numbers verified this session.

Note: **CURRENT_ISSUES.md is absent from the repo** (glob confirms), yet three tracking docs reference it — see New issues below.

## Confirmed still open

- bugs/long-junk-pages-pass-filters.md — Open; marker-catchable subset fixed by b59c8b7 (case-insensitive _block_markers + eight new markers, web.py:321) but the general case remains: pages with no matchable text pass all filters
- backlog/content-free-page-detection.md — Open; six observed junk pages contain no marker-matching text; structural gap in the marker approach
- backlog/search-module-level-state.md — Open; both defects still in code: shared _consecutive_search_failures counter across tasks (web.py:486) and orphaned fetch thread after wait_for timeout (web.py:294–296 cancels the await, not the thread)
- backlog/budget-rollover-unused-allocation.md — Open, High; per-task hard partition with no surplus→capped-task path (promoted from bugs/done/web-call-quota-exhausted-on-multi-entity-queries.md)
- backlog/dont-charge-quota-for-rejected-fetches.md — Open
- backlog/fetch-ceiling-timeout-frequency.md — Low, monitoring only
- backlog/file-based-coverage-gate.md — Open
- backlog/cross-searcher-completeness-gate.md — Open
- backlog/dedup-remember-blocked-urls.md — Open, Low
- backlog/direct-answer-fast-path.md — Open; fix home per doc: ASSESS COMPLEXITY section of ORCHESTRATOR_INSTRUCTIONS (src/prompts.py)
- backlog/multi-model-agent-routing.md — Open/future direction; "blocked" status rests on a stale prerequisite (see New issues)
- backlog/orchestrator-synthesis-anti-speculation.md — Open
- backlog/synthesis-salience-variance.md — Open
- backlog/tui-tool-calls-display.md — Open, cosmetic (raw XML tool-call rendering in src/engine/tui.py)
- backlog/vendor-price-fetch-httpx-hang-and-json.md — High-priority diagnosis; neither fix direction implemented — no forced HTTP/1.1 and no Shopify .json endpoint handling anywhere in web.py (grep confirms zero matches)
- backlog/whole-file-read-throughput.md — Open (Analyzer should grep-first, not read whole files)
- backlog/display-token-usage-on-completion.md — Open; no token-capture layer exists; references absent CURRENT_ISSUES.md
- backlog/general-vs-specific-task-decomposition.md — Backlog, High priority; candidate directions undecided
- backlog/report-artifact-naming-hardwired.md — Open, Low; final_report.md load-bearing at prompts.py:61/66/76/100, tui.py:1121/:1434, config_template.yaml:63

## Partially addressed

- bugs/reviewer-dies-delivering-verdict-on-long-report.md — diagnosis corrected (malform-then-500 fired 8× in one run hitting seven other sub-agents; not Reviewer-specific); better-targeted fix max_retries=3 committed at router.py:195 but untested live
- bugs/done/analyzer-selfinjects-control-syntax-from-source.md — marked Fixed/Done with Layer 1 explicitly unexercised; its open question now has a concrete code answer: the salvage handler exists at orchestrator.py:214–234 (catches QuotaAbortException from sub_agent.run, returns partial result incl. child results + workspace files); runtime confirmation still pending
- backlog/phase-3-review-correct-finalise.md — review→correct half present in code (tui.py:1121/:1135–1139 detect final_report.md and enforce mandatory review; tui.py:1489–1491 instruct correction by editing the existing file); draft/final split + rename NOT done — zero occurrences of report_draft anywhere in src/

## Appears resolved but not marked done

- backlog/dedup-fetches.md — status line "Done — pending live confirmation" but file still sits in backlog/, not done/; code present (web.py:157 ALREADY FETCHED, :349 DUPLICATE CONTENT)
- backlog/reapply-after-phase-rollback.md — FOR REVIEW checklist effectively executed item-by-item via individual bug fixes; verified present: _MIN_CONTENT_CHARS (web.py:53), 60s ceiling (:58/:294–296), SAVED_FILENAME + dedup (:157/:349), curl_cffi 429 mitigation (:167–174), case-insensitive markers (b59c8b7), _strip_image_markdown (:61/:335), loop breaker (core.py:48/117/162), truststore (pyproject.toml:16), salvage-on-abort (orchestrator.py:214), 1800s timeout + max_retries=3 (router.py:194–195); only af18dab (Analyzer list_workspace_files) absent — app.py:34 grants read/grep/think only. Doc never closed or updated

## New issues not yet tracked

- CLAUDE.md:74/77/99/147 documents report_draft.md as a current artifact; zero occurrences of "report_draft" in src/ (code writes final_report.md only — prompts.py:61, tui.py:1121). Doc/code drift with no tracking file
- CURRENT_ISSUES.md referenced by backlog/display-token-usage-on-completion.md, bugs/done/analyzer-selfinjects-control-syntax-from-source.md, and bugs/done/bandwidth-figures-unreconciled-across-report-sections.md — file absent from repo
- Stale prerequisite refs: backlog/multi-model-agent-routing.md and backlog/done/auto-prime-session-on-start.md cite bugs/simple-query-tool-call-malform as an open blocker; that bug is Done (LM Studio 0.4.18 rollback, no code change) → multi-model routing's "blocked" status may be stale
- Stale done record: backlog/done/phase-2-checklist-driven-gap-mop-up.md claims Done/validated live 2026-07-21 but its code (task_records extension a3004d6, checklist gate) is absent from src/ — zero matches for task_records/checklist; reapply-after-phase-rollback.md confirms Phase 2 commits deliberately NOT re-applied
- Stale closed-bug claim: bugs/done/quota-exhaustion-not-fed-back-to-delegation.md:69 says "8b6ce76 subsequently granted that tool" — current app.py:34 does NOT grant list_workspace_files to the Analyzer, so the "Requested function not found" error (events 1231/1232) can recur
- Untracked observation from bugs/done/web-call-quota-exhausted-on-multi-entity-queries.md: one delegate_tasks call received tasks as a 1052-char string instead of a list — flagged "worth a separate look", no tracking file exists
- Reviewer output-format non-compliance: noted in bugs/done/reviewer-overrides-fetched-sources.md (residual, declared out of scope) and backlog/general-vs-specific-task-decomposition.md ("never compliant across seven observed runs") — no dedicated tracking file
- Reviewer grep-loop evasion: backlog/done/multi-endpoint-router.md records a run where the Reviewer made 38 grep calls evading the alternating-pair loop detector; no bug/backlog file tracks this evasion case

## Verification notes (done records checked against current code)

Accurate as written: image-markdown-drowns-grep (_strip_image_markdown web.py:61, applied :335); fetch-timeout-not-hard-ceiling (:58/:294–296; residual tracked in search-module-level-state.md); junk-fetches-saved-as-sources (gate :339; constant now at :53, doc's line 48 predates file growth); orchestrator-collapses-named-entities (guard todos.py:38–69); quota-exhaustion-not-fed-back (_resolve_source_files present in orchestrator.py delegate_tasks — but see stale claim above); reviewer-overrides-fetched-sources (rule 8 at prompts.py:372); searcher-oversearches-until-cannot-fetch (SEARCH BLOCKED web.py:438); websearch-stall-no-return (shared window _next_allowed_search web.py:50/:542–543; tests/test_search_backoff.py present); fast-test-config-profile (config.py:81–85 real via _deep_merge); truststore-missing-dep (pyproject.toml:16); loop-breaker-validation (core.py raises QuotaAbortException :48/:117/:162 — behaviour has since hardened past the doc's "returns error, not hard-stop" caveat); auto-prime-session-on-start (throwaway Hello turn tui.py:487 present; closing line stale per New issues); multi-endpoint-router (router.py matches as-built record incl. max_retries=3 :195 and TASK FAILED log with endpoint URL).
