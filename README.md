# Deep Research Agent

A hierarchical deep research agent built with the **Microsoft Agent Framework** and **Textual** TUI. Uses a strict delegation chain — **Orchestrator → Searcher → Analyzer** for research, plus a post-research **Reviewer** — to perform web-based research and document analysis while keeping context windows lean for local LLMs.

## Architecture

```
+-----------------------------------+
|    Orchestrator (Planner)         |
|-----------------------------------|
| Tools: write_workspace_file,      |
|        list_workspace_files,      |
|        write_todos, read_todos,   |
|        think_tool, delegate_tasks |
| No web or file reading tools.     |
+--------+----------------+---------+
         | delegates to   | delegates to (Phase 3)
         v                v
+--------------------+   +--------------------+
|   Searcher         |   |   Reviewer (Leaf)  |
|--------------------|   |--------------------|
| Tools: web_search, |   | Tools: read_file,  |
|        fetch_url,  |   |        grep_file,  |
|        think_tool, |   |        think_tool  |
|        delegate    |   | No web, no delegate.|
| No file reading.   |   | Reviews the draft; |
+--------+-----------+   | flags concerns back |
         | delegates to  | to the Orchestrator.|
         v               +--------------------+
+--------------------+
|   Analyzer (Leaf)  |
|--------------------|
| Tools: read_file,  |
|        grep_file,  |
|        think_tool  |
| No web, no delegate.|
+--------------------+
```

### Delegation Chain & Tool Separation

- **Orchestrator**: Plans research, dispatches Searchers, synthesizes `final_report.md`. Has NO web tools and NO file reading tools. Delegates ONLY to the Searcher.
- **Searcher**: Searches the web, fetches URLs to the workspace. Has NO file reading tools — forced to delegate to the Analyzer. Delegates ONLY to the Analyzer.
- **Analyzer**: Reads and extracts data from downloaded files. Has NO web tools and NO delegation capability. Leaf node.
- **Reviewer**: Fact-checks the draft report in a dedicated review phase (Phase 3). Has only `read_workspace_file`, `grep_workspace_file`, and `think_tool` — NO web tools and NO delegation. Leaf node. Returns a numbered list of integrity concerns (or `REVIEW PASSED`); it does not research or rewrite. The Orchestrator owns any corrective research and the final report.

This separation prevents any single agent from bloating its context window with raw web content.

### Review & Report Finalisation (Phase 3)

After research completes, the Orchestrator writes a draft report and runs a review-and-correct loop before finalising:

1. **Draft.** The Orchestrator writes `report_draft.md`.
2. **Review.** It delegates the draft to the Reviewer, which returns integrity concerns (or `REVIEW PASSED`). The Reviewer never researches, rewrites, or calls Searchers.
3. **Corrective research.** For material, quickly-fixable concerns, the Orchestrator runs a single bounded corrective pass via the Searcher, spending from the reserved budget. Concerns that cannot be quickly resolved stay as honest gaps; data is never invented to satisfy a concern.
4. **Final report.** The Orchestrator writes `final_report.md` as a fresh file, always — even on a clean `REVIEW PASSED`. `report_draft.md` is left in place, so the draft/final pair gives traceability of exactly what review changed.

### Proportional Search Depth

The Orchestrator assesses query complexity before planning:
- **Simple factual queries**: Dispatch a single Searcher. One authoritative source is sufficient.
- **Multi-fact queries**: A single Searcher is still sufficient.
- **Comparative/synthesis queries**: Dispatch one Searcher per independent angle, concurrently.
- **Deep research**: Full multi-phase approach with multiple delegations.

### Source Quality Awareness

The Searcher evaluates source authority:
- **Authoritative** (official docs, spec sheets): One source is sufficient.
- **Semi-authoritative** (established publications): One is usually enough, a second is welcome.
- **Informal** (forums, blogs): Corroborate with at least one additional source.

### Session Isolation

Each run gets a timestamped isolated folder (e.g., `run_1748192400/`). File tools automatically map all operations into this folder. Agents are unaware of the run folder and read/write files directly.

## Setup Instructions

### 1. Create the Environment & Install

```bash
cd /home/kyuz0/video/deep-research
python -m venv venv
source venv/bin/activate
pip install -e .
```

**System-Wide Installation (Optional):**

```bash
pipx install .
```

### 2. Configure Endpoints

By default, the application uses an OpenAI-compatible API on `localhost:8080` (e.g., `llama.cpp`). Create a `.env` file:

```env
OPENAI_API_BASE=http://localhost:8080/v1
OPENAI_API_KEY=dummy
OPENAI_MODEL=local-model
```

### 3. Configure the Agent

On first run, the config is auto-created at `~/.deep-research-agent/config.yaml` from `src/config_template.yaml`. Key settings:

> **Note:** `web_search` and `fetch_url_to_workspace` no longer have separate quotas. They draw from a single unified `web_calls` pool, allocated per-task by weight (`allocation`), with `reserve` (under `web_calls.rules`) held back for the Phase 3 corrective pass. Quotas are GLOBAL — shared across all agents — and each key must be unique.

```yaml
settings:
  enable_thinking: false         # LLM reasoning traces on/off
  max_review_rounds: 2           # Max enforced review rounds after the final report
                                 # (Reviewer checks, Orchestrator fixes). Capped to
                                 # guarantee termination. 2 recommended.
  concurrency:
    max_concurrent_tasks: 3      # Max parallel sub-agent execution
  quotas:                        # Global tool call limits (shared across ALL agents)
    delegate_tasks: 20
    web_calls:                   # Unified search + fetch budget (shared pool)
      limit: 100
      rules:
        reserve: 10              # Held back for post-review corrective research
    write_workspace_file: 20
    write_todos: 30
    read_todos: 30
    think_tool: 30
    read_workspace_file:
      limit: 60
      rules:
        max_lines: 400           # Per-read line-slice cap
    grep_workspace_file:
      limit: 60
      rules:
        max_matches: 15          # Max matches returned per grep
    list_workspace_files: 20
  fast_test:
    enabled: false               # Reduced quotas for quick smoke tests
    overrides:                   # Applied only when fast_test.enabled is true
      concurrency:
        max_concurrent_tasks: 1
      quotas:
        web_calls:
          limit: 30
        delegate_tasks: 12
        read_workspace_file:
          limit: 15
        grep_workspace_file:
          limit: 15
        write_workspace_file: 5
  allocation:                    # Weighted per-task web_calls allocation
    flatness_constant: 7         # Higher = more even split across tasks
    floor: 6                     # Minimum web_calls guaranteed per task
  enable_conversational_memory: true
  enable_session_persistence: true
  workspace:
    type: disk                   # "memory" or "disk"
    dir: "~/.{APP_NAME}/workspace"
    session_isolation: true      # Timestamped run folders (e.g. run_1748192400/)
    required_artifact: "final_report.md"
```

### 4. Run the TUI

```bash
python src/app.py
```

### 5. Headless Mode

```bash
python src/app.py --prompt "Compare the AI research strategies of OpenAI, Google DeepMind, and Anthropic in 2024." --auto-approve
```

**Useful Flags:**
- `--prompt "..."`: Run headlessly with a specific query.
- `--auto-approve`: Bypass Human-in-the-Loop tool approvals (required for headless).
- `--list-sessions`: List saved session histories.
- `--resume <session_id>`: Restore a previous session.
- `/toggle_thinking`: Toggle LLM reasoning traces in the TUI.
- `/files`: Browse workspace files in the TUI.

## Included Tools

| Tool | Description |
|------|-------------|
| `web_search` | DuckDuckGo search (no API key needed) — charges the unified `web_calls` pool |
| `fetch_url_to_workspace` | Fetch URLs → parse to Markdown → save to workspace — charges the unified `web_calls` pool |
| `read_workspace_file` | Read files with line-range chunking |
| `grep_workspace_file` | Regex search within workspace files |
| `write_workspace_file` | Write files to workspace |
| `list_workspace_files` | List all workspace files |
| `write_todos` / `read_todos` | Markdown checkbox task tracking |
| `think_tool` | Forced reflection pause for structured reasoning |
| `delegate_tasks` | Auto-injected for agents with children |

Report artifacts: `report_draft.md` (written after research, before review) and `final_report.md` (written after review and any corrective fixes). Both persist for traceability.

## Security

- **No shell execution**: The `run_shell_command` tool is removed from this agent.
- **Quota enforcement**: Every tool has a global call limit to prevent infinite loops.
- **Session isolation**: Each run is sandboxed into its own timestamped folder.
- **Anti-looping directives**: Baked into all agent system prompts to prevent infinite retry cycles.
