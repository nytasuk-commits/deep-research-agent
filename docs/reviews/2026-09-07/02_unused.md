# Pass 2 — Unused Code (2026-09-07)

Scope: unused imports, functions, config keys, dead branches. Source files under `src/` re-read fresh; every symbol verified by repo-wide grep before inclusion.

## Findings

- src/utils/parsers.py:3 — `import httpx` never referenced anywhere in the module (high)
- src/utils/parsers.py:30-44 — extract_advanced_pdf() defined with zero callers repo-wide; web.py implements liteparse inline instead (high)
- src/tools/web.py:186 — redundant boolean clause `("application/pdf" in content_type and is_actual_pdf)`; A∨(B∧A)≡A, whole expression reduces to is_actual_pdf alone (high)
- src/tools/web.py:481-482 — dead branch `elif provider == "tavily": pass  # Removed Tavily placeholder`; config search_provider=tavily silently yields "Found 0 result(s)" with no warning (high)
- src/engine/orchestrator.py:1 — `import os` never referenced; no os.* usage in the module (high)
- src/engine/orchestrator.py:5 — OpenAIChatCompletionClient imported but never used (the type hint lives in router.py, not here) (high)
- src/engine/orchestrator.py:7 — WORKSPACE_TOOLS imported from tools; only occurrence outside the import is a comment at line 383, no code usage (high)
- src/engine/router.py:220-222 — EndpointRouter.endpoint_count() has zero callers repo-wide (peak_summary and inflight_snapshot are used; this one is not) (high)
- src/engine/tui.py:12 — module-level `from agent_framework import Message, Content` is dead: every use site is shadowed by local imports at lines 926/1099 (ui_callback), 1275 (cli_subagent_callback), 1398 (run_cli) (high)
- src/engine/tui.py:16 — `import re` never referenced; no re.* usage in the module (high)
- src/engine/tui.py:21 — module-level WORKSPACE_TOOLS import is dead: both use sites (lines 950, 1083) sit inside ui_callback where local imports at lines 927/1082 shadow it (high)
- src/engine/tui.py:229 — redundant local `import json` in ApprovalWidget.compose; json already imported module-level at line 10 (high)
- src/engine/tui.py:734,781 — duplicate local `import time` twice inside handle_agent_update (same function scope); the file has no module-level time import at all (high)
- src/engine/tui.py:926-927 — local imports in ui_callback (`Message, Content`; `WORKSPACE_TOOLS`) shadow the module-level imports at lines 12/21, which is what makes those dead; one layer should be dropped (high)
- src/engine/tui.py:1082 — second `from tools import WORKSPACE_TOOLS` in ui_callback, duplicating the identical local import at line 927 in the same function scope (high)
- src/engine/tui.py:1099 — duplicate `from agent_framework import Content`; already imported locally at line 926 in the same function scope (and module-level at line 12) (high)
- src/engine/tui.py:1275,1398 — local `from agent_framework import Message` in cli_subagent_callback and run_cli; redundant with the module-level import at line 12 (which is otherwise dead) (high)
- src/engine/tui.py:1459 — local `from tools.fs import get_workspace_files` in run_cli; redundant with the module-level import at line 21 (still alive via _show_file_picker, line 1165) (high)
- src/engine/tui.py:1545 — local `import json` in cli_main list_sessions path; redundant with module-level line 10 (high)
- src/tools/todos.py:4 — `_get_workspace_dir` imported from tools.fs but never used anywhere in the module (high)

## Ruled out after verification (NOT unused)

- src/prompts.py:399 SUBAGENT_INSTRUCTIONS alias — used at orchestrator.py:8, 173
- src/utils/parsers.py convert_to_markdown — used at web.py:208, 221
- src/config.py save_config() — called from tui.py:572, 579
- src/config.py fast_test overrides (lines 81-85) — genuinely merged into cfg via _deep_merge, not a dead branch
- src/engine/router.py inflight_snapshot() — used by tests/test_router.py (lines 120, 156, 192, 221)
- src/engine/orchestrator.py reset_session() — called from tui.py:558, 661, 1336
- All config_template.yaml keys — each is read somewhere in code (max_review_rounds and required_artifact only on the headless path, but still consumed)

## Totals

20 findings, all high confidence. No unused config keys found; no medium/low-confidence items remained after verification.
