# Code Review — 2026-09-07

## Summary

Four passes over `src/` plus a cross-reference of every tracking doc: **75 code findings** (41 quality, 20 unused-code, 14 efficiency) and **32 backlog/bug cross-reference items** (19 confirmed still open, 3 partially addressed, 2 resolved-but-unmarked-done, 8 new issues not yet tracked).
Highest-impact code item: `tui.py` `_write_log()` rewrites the entire session JSON on every stream chunk (quadratic I/O over a long session); secondary costs are repeated full-content reads for metadata and fresh HTTP clients per operation.
Most urgent tracking-doc issue: CLAUDE.md documents a `report_draft.md` artifact that does not exist in `src/`, CURRENT_ISSUES.md is referenced by three docs but absent from the repo, and three done-records are stale against current code (Phase 2 rollback, Analyzer tool grant, simple-query prerequisite).

## Code Quality Issues

(from 01_quality.md — 41 findings: 17 medium, 24 low)

- src/app.py:60 — Orchestrator tool list includes read_workspace_file, contradicting CLAUDE.md ("No web or file reading tools") and the prompts.py header comment (medium)
- src/app.py:51 — Reviewer is granted list_workspace_files beyond its documented set (read/grep/think) (low)
- src/config.py:6-18 — parses sys.argv for --config/-c at import time; importing the module mutates global state (medium)
- src/config.py:140 — auto-calls load_config() on import; file read/create side effect from a plain import (medium)
- src/config.py:90 — OPENAI_MODEL env override applies only while config is still at its default, making precedence surprising (low)
- src/engine/orchestrator.py:307 — delegate_tasks tool closure redefined inside every create_local_agent() call (line 69); a fresh tool object per agent instead of one shared definition (low)
- src/engine/orchestrator.py:85-89,262-268,381-385 — three near-identical [!CAUTION] boilerplate comment blocks duplicated across agent definitions (low)
- src/engine/router.py:475-476 — _probe swallows all exceptions (`except Exception: return False`) with no logging; a programming error is indistinguishable from an endpoint being down (medium)
- src/engine/router.py:276,449 — backoff index computation `min(fail_count - 1, len(_BACKOFF) - 1)` duplicated in _prime_if_needed and _mark_probe_failed (low)
- src/engine/tui.py:26-29 — module-level mutable globals (_session_events, _current_call_by_source, _current_text_by_source, _current_session_id) shared across sessions; state leaks between runs in one process (medium)
- src/engine/tui.py:50-51,56-57 — _write_log swallows all exceptions (`except Exception: pass`); session-persistence failures are invisible (low)
- src/engine/tui.py:47 — reaches into private orchestrator_module._session across a module boundary (low)
- src/engine/tui.py:188-189 — bare `except Exception: pass` in PromptInput.on_key hides key-handling errors (low)
- src/engine/tui.py:251,303,338 — DOTS_FRAMES list triple-duplicated across ThinkingWidget/ProcessingWidget/ToolCallWidget (low)
- src/engine/tui.py:690,773 — nested function apply_depth_style defined identically twice (reconstruct_ui_from_events and handle_agent_update) (low)
- src/engine/tui.py:950-956 vs 1083-1090 — approval tool-execution logic (WORKSPACE_TOOLS lookup + parse_arguments + call) duplicated between ui_callback and the main loop; divergence risk (medium)
- src/engine/tui.py:940-946,1072-1078 — target-widget fallback lookup (match by tool_name, not done) duplicated in both approval paths (low)
- src/engine/tui.py:459,618,930,1060,1278,1384,1448 — `getattr(config, 'AUTO_APPROVE', False)` repeated 7 times with no single accessor (low)
- src/engine/tui.py:603,1198,1327,1548 — open() without encoding="utf-8" while other opens specify it; on Windows the cp1252 default can corrupt session JSON containing unicode (medium)
- src/engine/tui.py:900 — session_dir_ctx.set(...) token is never reset; the only reset (line 1513) belongs to run_cli's separate token (line 1268), so the TUI-path contextvar leaks for the rest of the process (medium)
- src/engine/tui.py:1134,1484 — review_phase_ctx.set(True) with no saved/reset token; once set it stays True for the remainder of that context in both TUI and headless paths (medium)
- src/engine/tui.py:1127 — review_done detection scans all _session_events for the substring "Reviewer" inside delegate_tasks argument strings; fragile heuristic, any mention triggers it (medium)
- src/engine/tui.py:1436 — `update` referenced after the async-for loop; if the stream yields no updates this is an unbound-variable NameError escaping as BaseException (low)
- src/engine/tui.py:1438-1442 — QuotaAbortException detected by string comparison of type name (`type(e).__name__ == ...`) instead of importing the class; forces a broad `except BaseException` (medium)
- src/engine/tui.py:487 — auto-prime throwaway "Hello" turn on fresh sessions, a workaround for Qwen XML chat-template malformation; fragile coupling to model-specific behaviour (documented) (low)
- src/tools/core.py:25 — QuotaAbortException inherits BaseException instead of Exception; bypasses every `except Exception` handler and forces string-name checks at call sites (medium)
- src/tools/core.py:185-207 — with_quota's async_wrapper/sync_wrapper are near-duplicate bodies (quota check + repeat check + traceback wrapper) (low)
- src/tools/core.py:173-175 — _check_repeat catches all exceptions and returns None (allow); loop detection silently disabled on any internal failure, no logging (low)
- src/tools/fs.py:22 — `".." in filename` blocks any path containing ".." anywhere, including legitimate names like "a..b.md"; over-broad guard (low)
- src/tools/fs.py:137-138,158-159,205-206,225-226 — every tool handler embeds full traceback.format_exc() in the string returned to the LLM; leaks internal paths and bloats context (low)
- src/tools/web.py:148 — mixed `or`/`and` without parentheses (`... or url.lower().find(...) != -1 and "/" in _dom`); precedence-dependent, intent unclear (medium)
- src/tools/web.py:259 — paywall heuristic requires the substring "false" anywhere on the page; false positives on any text containing e.g. "falsehoods" (medium)
- src/tools/web.py:294-296 — wait_for timeout returns FETCH TIMEOUT but the fetch thread keeps running orphaned, holding resources until it finishes (tracked in backlog/search-module-level-state.md) (medium)
- src/tools/web.py:371-374 — with session isolation off, the dedup registry is keyed by an empty run_key and persists across runs within one process; URLs fetched in a prior run are reported "ALREADY FETCHED" (medium)
- src/tools/web.py:398,417 — web_search lacks @with_quota and calls check_quota("web_search") manually, skipping _check_repeat loop detection and the CRITICAL TOOL EXECUTION ERROR wrapper; inconsistent with every other tool (medium)
- src/tools/web.py:484 — `chr(10).join` instead of "\n".join; obscure style (low)
- src/utils/parsers.py:27-28 — `except Exception as e: return None` swallows all parse errors (variable unused); callers cannot distinguish "no content" from "parse failure" (low)
- src/prompts.py:52-64 — header comment says the Orchestrator has NO read_workspace_file, but the prompt body at line 64 lists it; internal contradiction matching app.py:60 (medium)
- src/prompts.py:246-247 — {web_search_quota}/{fetch_url_to_workspace_quota} placeholders are tied to legacy per-tool config keys while current config uses a unified web_calls pool; if those keys are absent the placeholders stay unsubstituted in the rendered prompt (medium)
- src/prompts.py:328 — same variable {read_workspace_file_quota} repeated twice in one sentence ("maximum calls (max ... reads total)") (low)

## Unused Code

(from 02_unused.md — 20 findings, all high confidence)

- src/utils/parsers.py:3 — `import httpx` never referenced anywhere in the module
- src/utils/parsers.py:30-44 — extract_advanced_pdf() defined with zero callers repo-wide; web.py implements liteparse inline instead
- src/tools/web.py:186 — redundant boolean clause `("application/pdf" in content_type and is_actual_pdf)`; A∨(B∧A)≡A, whole expression reduces to is_actual_pdf alone
- src/tools/web.py:481-482 — dead branch `elif provider == "tavily": pass  # Removed Tavily placeholder`; config search_provider=tavily silently yields "Found 0 result(s)" with no warning
- src/engine/orchestrator.py:1 — `import os` never referenced; no os.* usage in the module
- src/engine/orchestrator.py:5 — OpenAIChatCompletionClient imported but never used (the type hint lives in router.py, not here)
- src/engine/orchestrator.py:7 — WORKSPACE_TOOLS imported from tools; only occurrence outside the import is a comment at line 383, no code usage
- src/engine/router.py:220-222 — EndpointRouter.endpoint_count() has zero callers repo-wide (peak_summary and inflight_snapshot are used; this one is not)
- src/engine/tui.py:12 — module-level `from agent_framework import Message, Content` is dead: every use site is shadowed by local imports at lines 926/1099 (ui_callback), 1275 (cli_subagent_callback), 1398 (run_cli)
- src/engine/tui.py:16 — `import re` never referenced; no re.* usage in the module
- src/engine/tui.py:21 — module-level WORKSPACE_TOOLS import is dead: both use sites (lines 950, 1083) sit inside ui_callback where local imports at lines 927/1082 shadow it
- src/engine/tui.py:229 — redundant local `import json` in ApprovalWidget.compose; json already imported module-level at line 10
- src/engine/tui.py:734,781 — duplicate local `import time` twice inside handle_agent_update (same function scope); the file has no module-level time import at all
- src/engine/tui.py:926-927 — local imports in ui_callback (`Message, Content`; `WORKSPACE_TOOLS`) shadow the module-level imports at lines 12/21, which is what makes those dead; one layer should be dropped
- src/engine/tui.py:1082 — second `from tools import WORKSPACE_TOOLS` in ui_callback, duplicating the identical local import at line 927 in the same function scope
- src/engine/tui.py:1099 — duplicate `from agent_framework import Content`; already imported locally at line 926 in the same function scope (and module-level at line 12)
- src/engine/tui.py:1275,1398 — local `from agent_framework import Message` in cli_subagent_callback and run_cli; redundant with the module-level import at line 12 (which is otherwise dead)
- src/engine/tui.py:1459 — local `from tools.fs import get_workspace_files` in run_cli; redundant with the module-level import at line 21 (still alive via _show_file_picker, line 1165)
- src/engine/tui.py:1545 — local `import json` in cli_main list_sessions path; redundant with module-level line 10
- src/tools/todos.py:4 — `_get_workspace_dir` imported from tools.fs but never used anywhere in the module

## Efficiency Opportunities

(from 03_efficiency.md — 14 findings: 1 high, 5 medium incl. two medium/high, 7 low/low-medium, 1 negligible)

- src/engine/tui.py:31–57 — `_write_log()` rewrites the ENTIRE session JSON on every call; called from log_stream_content :148 (i.e. on EVERY stream chunk) among others — high: O(session size) disk write per token chunk; total I/O grows quadratically over a long session
- src/tools/fs.py:163–171 — `list_workspace_files` reads every file's full content via get_workspace_file_content(:169) just to compute line/char counts for the listing; quota-charged tool agents call repeatedly — medium/high: full read of the entire fetched corpus per call
- src/engine/tui.py:1172–1175 — `_show_file_picker` calls get_workspace_file_content(f) for EVERY workspace file just to compute byte counts for picker rows — medium/high: reads the whole fetched corpus on /files
- src/tools/web.py:163 — module-level convenience call httpx.get(...) creates a fresh client + connection pool per fetch; no keep-alive reuse across URLs within one task — medium: TCP+TLS setup cost paid on every URL
- src/tools/web.py:236, 287–289 — BeautifulSoup re-parses the full HTML document after markitdown already parsed it (JSON script-blob extraction at :236); a second full parse again in the fallback path (:287–289) — medium: full DOM build ×2 per page
- src/engine/tui.py:601–604, 1196–1199, 1546–1549 — /sessions (top 10), _show_session_picker (top 15) and cli list_sessions (top 10) each do a full open+json.load of every listed session file just to extract timestamp/session_id — medium: O(N × file size) on every listing
- src/tools/core.py:81 — `_check_repeat` runs json.dumps(sig_data, sort_keys=True) over full args+kwargs on EVERY tool call; for write_workspace_file this serializes the entire file content (40KB+ reports) on each write — low/medium
- src/engine/router.py:463–476 — `_probe` creates a fresh httpx.AsyncClient(timeout=10.0) per probe; the 5s poll loop probes every down endpoint each iteration, so one client is built and torn down per endpoint per cycle — low/medium
- src/tools/web.py:321 — `any(m.lower() in data.lower() for m in _block_markers)` recomputes .lower() on both the marker AND the full page text once per marker, instead of lowercasing the page once before the loop — low/medium
- src/engine/tui.py:1124–1129 — review_done detection scans ALL accumulated _session_events for the substring "Reviewer" inside delegate_tasks argument strings; runs on every agent-turn completion — low: O(events × arg length) per turn, grows with session length
- src/tools/web.py:453–458 — `_sanitize_snippet` runs six sequential regex passes over every search-result snippet (× max_results snippets per web_search call) — low
- src/tools/fs.py:42–52 — `get_workspace_files()` re-runs os.walk(d) on every call with no caching between calls within one turn — low
- src/tools/web.py:199–202 — blocking subprocess.run(["liteparse", tmp_path], timeout=60) inside the fetch thread; acceptable given the thread isolation (the 60s wait_for ceiling depends on it) but up to 60s of CPU-bound work per PDF with no progress signal — low
- src/engine/orchestrator.py:153 — copy.deepcopy(_parent_quota) per delegated task; dict is small so cost is negligible, noted for completeness — negligible

## Backlog/Bug Cross-Reference

(from 04_backlog_crossref.md — 32 items; CURRENT_ISSUES.md absent from repo but referenced by three docs)

**Confirmed still open (19):** bugs/long-junk-pages-pass-filters (marker subset fixed by b59c8b7, general case remains); backlog/content-free-page-detection (six junk pages with no matchable text); backlog/search-module-level-state (both defects in code: shared _consecutive_search_failures web.py:486; orphaned fetch thread web.py:294–296); backlog/budget-rollover-unused-allocation (High, per-task hard partition); backlog/dont-charge-quota-for-rejected-fetches; backlog/fetch-ceiling-timeout-frequency (Low, monitoring); backlog/file-based-coverage-gate; backlog/cross-searcher-completeness-gate; backlog/dedup-remember-blocked-urls (Low); backlog/direct-answer-fast-path; backlog/multi-model-agent-routing (blocked on stale prerequisite); backlog/orchestrator-synthesis-anti-speculation; backlog/synthesis-salience-variance; backlog/tui-tool-calls-display (cosmetic); backlog/vendor-price-fetch-httpx-hang-and-json (High, neither fix direction implemented — no HTTP/1.1 forcing or Shopify .json handling in web.py); backlog/whole-file-read-throughput; backlog/display-token-usage-on-completion (no capture layer exists); backlog/general-vs-specific-task-decomposition (High, directions undecided); backlog/report-artifact-naming-hardwired (Low, final_report.md load-bearing at prompts.py:61/66/76/100, tui.py:1121/:1434, config_template.yaml:63).

**Partially addressed (3):** bugs/reviewer-dies-delivering-verdict-on-long-report (diagnosis corrected; max_retries=3 committed at router.py:195 but untested live); bugs/done/analyzer-selfinjects-control-syntax-from-source (marked Fixed/Done, Layer 1 unexercised — salvage handler exists at orchestrator.py:214–234, runtime confirmation pending); backlog/phase-3-review-correct-finalise (review→correct half present in tui.py:1121/:1135–1139/:1489–1491; draft/final split NOT done — zero occurrences of report_draft in src/).

**Appears resolved but not marked done (2):** backlog/dedup-fetches ("Done — pending live confirmation" but still in backlog/, not done/; code present web.py:157/:349); backlog/reapply-after-phase-rollback (FOR REVIEW checklist effectively executed item-by-item via individual bug fixes — all clean candidates verified present except af18dab Analyzer list_workspace_files, absent at app.py:34; doc never closed).

**New issues not yet tracked (8):** CLAUDE.md:74/77/99/147 documents report_draft.md as a current artifact but zero occurrences in src/ (doc/code drift); CURRENT_ISSUES.md referenced by three tracking docs, absent from repo; stale prerequisite refs — multi-model-agent-routing + auto-prime-session-on-start cite simple-query-tool-call-malform as open blocker though it is Done (LM Studio 0.4.18 rollback); stale done record — phase-2-checklist-driven-gap-mop-up claims Done/validated but its code (task_records/checklist gate) is absent from src/, Phase 2 commits deliberately not re-applied; stale closed-bug claim — quota-exhaustion-not-fed-back:69 says the Analyzer tool grant "should not recur" but app.py:34 does not grant list_workspace_files, so the error can recur; untracked observation — delegate_tasks received tasks as a 1052-char string instead of a list (flagged in web-call-quota-exhausted, no tracking file); Reviewer output-format non-compliance noted in two docs ("never compliant across seven observed runs"), no dedicated tracking file; Reviewer grep-loop evasion (38 calls evading the alternating-pair detector) recorded in multi-endpoint-router.md, untracked.
