# Display upload/download token usage on run completion

**Status:** Open (backlog)
**Type:** Feature / observability

## Goal

After a run completes, show the total tokens consumed — input (upload) and output (download) — either in the final report, in the TUI, or both.

## Current state

No token usage is captured anywhere in the codebase. A grep for `usage` / `input_tokens` / `output_tokens` / `prompt_tokens` / `completion_tokens` finds only contextvar plumbing and unrelated prompt text. There is no capture layer and no aggregation. This item is therefore CAPTURE-THEN-DISPLAY, not just display.

## Data source

The model responses already carry per-response usage. Session JSON logs show each Anthropic response includes a `usage` block with `input_tokens`, `output_tokens`, and `cache_read_input_tokens`. The data exists per-call; nothing reads or sums it.

## Scope

1. **Capture:** Read the `usage` block from each model response as it streams/completes.
2. **Aggregate:** Accumulate input and output tokens across the whole run, across all agents (Orchestrator, Searchers, Analyzers, Reviewer). Decide whether to also track `cache_read_input_tokens` separately.
3. **Display:** Surface run totals on completion. Options (pick one or both):
   - **TUI:** a summary line when the run finishes (e.g. "Tokens — in: X, out: Y").
   - **Final report:** a footer line recording token cost of the run.

## Open decisions

- Per-agent breakdown, or run-total only? (Per-agent needs attribution the flat log currently makes hard — see the converged-runtimes/flat-rendering note in CURRENT_ISSUES.md.)
- Report footer vs TUI vs both.
- Whether to include cache-read tokens in the headline number or show them separately.

## Acceptance

- On run completion, total input and output tokens for the run are shown.
- Figures are sourced from actual model `usage` data, not estimated.
- No change to research behaviour or quotas — this is observability only.
