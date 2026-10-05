# Pass 3 — Efficiency (2026-09-07)

Scope: redundant calls, unnecessary loops, blocking ops that could be async, repeated work. Source files under `src/` re-read fresh; every line number verified against the current file before inclusion.

## Findings

- src/engine/tui.py:31–57 — `_write_log()` rewrites the ENTIRE session JSON (`json.dump(payload, f, indent=2)` of all accumulated `ui_events` plus a fresh `orchestrator_module._session.to_dict()` at :49) on every call; called from log_prompt :69, log_stream_content :148 (i.e. on EVERY stream chunk), /toggle_persistence :587, run_agent post-stream :1025 and abort path :1043, run_cli :1504 — high: O(session size) disk write per token chunk; total I/O grows quadratically over a long session
- src/tools/fs.py:163–171 — `list_workspace_files` reads every file's full content via `get_workspace_file_content(k)` (:169) just to compute line/char counts for the listing; it is a quota-charged tool agents call repeatedly (Analyzer prompts instruct calling it on any not-found filename) — medium/high: full read of the entire fetched corpus per call
- src/engine/tui.py:1172–1175 — `_show_file_picker` calls `get_workspace_file_content(f)` for EVERY workspace file just to compute byte counts for picker rows — medium/high: reads the whole fetched corpus on `/files`
- src/tools/web.py:163 — module-level convenience call `httpx.get(url, headers=headers, timeout=30, follow_redirects=True)` creates a fresh client + connection pool per fetch; no keep-alive reuse across URLs within one task — medium: TCP+TLS setup cost paid on every URL
- src/tools/web.py:236, 287–289 — BeautifulSoup re-parses the full HTML document after markitdown already parsed it (JSON script-blob extraction at :236); a second full parse again in the fallback path (:287–289) — medium: full DOM build ×2 per page
- src/engine/tui.py:601–604, 1196–1199, 1546–1549 — /sessions (top 10), _show_session_picker (top 15) and cli list_sessions (top 10) each do a full `open`+`json.load` of every listed session file just to extract timestamp/session_id — medium: O(N × file size) on every listing, while the data is already written whole by `_write_log()`
- src/tools/core.py:81 — `_check_repeat` runs `json.dumps(sig_data, sort_keys=True)` over full args+kwargs on EVERY tool call; for write_workspace_file this serializes the entire file content (40KB+ reports) on each write — low/medium: O(content size) serialization per large write
- src/engine/router.py:463–476 — `_probe` creates a fresh `httpx.AsyncClient(timeout=10.0)` per probe; the 5s poll loop (:487) probes every down endpoint each iteration, so one client is built and torn down per endpoint per cycle — low/medium
- src/tools/web.py:321 — `any(m.lower() in data.lower() for m in _block_markers)` recomputes `.lower()` on both the marker AND the full page text (up to ~20KB) once per marker, instead of lowercasing the page once before the loop — low/medium
- src/engine/tui.py:1124–1129 — review_done detection scans ALL accumulated `_session_events` for the substring "Reviewer" inside delegate_tasks argument strings; runs on every agent-turn completion in run_agent — low: O(events × arg length) per turn, grows with session length
- src/tools/web.py:453–458 — `_sanitize_snippet` runs six sequential regex passes over every search-result snippet (× max_results snippets per web_search call) — low
- src/tools/fs.py:42–52 — `get_workspace_files()` re-runs `os.walk(d)` on every call; called from tui.py:1120/:1165, orchestrator.py:217/:281, tui.py:1459 with no caching between calls within one turn — low
- src/tools/web.py:199–202 — blocking `subprocess.run(["liteparse", tmp_path], ..., timeout=60)` inside the fetch thread; acceptable given the thread isolation (the 60s wait_for ceiling depends on it) but adds up to 60s of CPU-bound work per PDF with no progress signal — low
- src/engine/orchestrator.py:153 — `copy.deepcopy(_parent_quota)` per delegated task; dict is small so cost is negligible, noted for completeness — negligible

## Ruled out after verification (NOT an efficiency issue)

- src/utils/parsers.py:7 — MarkItDown() instantiated once at module import and reused by convert_to_markdown; no per-call construction
- src/engine/orchestrator.py:305–307 — delegate_tasks closure redefined per create_local_agent(); one-time setup cost, not repeated work (quality/duplication concern, covered in 01_quality.md)
- src/tools/todos.py:43–62 — named-entity validation recomputes e.lower() per line; bounded by a handful of entities × todo lines, negligible

## Totals

14 findings: 1 high, 5 medium (incl. two medium/high), 7 low/low-medium, 1 negligible. Dominant cost is the per-chunk full-file session rewrite in tui.py `_write_log()`; secondary costs are repeated full-content reads for metadata (fs.py list_workspace_files, tui.py _show_file_picker) and fresh HTTP client creation per operation (web.py:163, router.py:472).
