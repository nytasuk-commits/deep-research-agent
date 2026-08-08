# Simple/Ambiguous Queries Malform Tool Calls

**Status:** Done — root cause was LM Studio 0.4.20 regression; resolved by rollback to 0.4.18
**Type:** Bug
**Source:** Observed in run

## Summary
Bare queries like "Compare X and Y" caused the model to emit malformed tool calls (`?????` output / raw XML leaking as content) and stall; well-framed research queries appeared to work. Originally theorised as a streaming-specific chat-template parse failure. Actual root cause was an LM Studio version regression.

## Root cause (confirmed)
LM Studio auto-updated overnight to version 0.4.20, which introduced a regression in its Anthropic endpoint's handling of Qwen chat templates under large agentic payloads. This produced garbage `?` output and malformed tool calls. Rolling LM Studio back to 0.4.18 resolved the issue completely. Confirmed by A/B: 0.4.20 broke, 0.4.18 clean; a clean gpt-oss-20b run through Claude Code on the good version returned a well-formed structured tool call.

## Resolution
- Rolled LM Studio back to 0.4.18.
- Pinned to LM Studio 0.4.18 (there is no auto-update toggle in LM Studio; recurrence is avoided by not manually updating).
- Verified: post-rollback runs produce well-formed tool-call streams on both simple and complex queries.

## Superseded analysis (kept for history)
Earlier investigation attributed the malform to a streaming-specific bug in LM Studio's chat-template handling (raw Qwen XML tokens leaking through as content only when `stream=True`), and proposed two fixes: Path A (swap the chat template) and Path B (make the app request non-streaming). These were never applied. The version rollback resolved the observed malform without either path. If a streaming-specific malform recurs on a known-good LM Studio version, revisit Path A/B.

## Related
- LM Studio version pinning (0.4.18 known good; 0.4.20 regressed)
- backlog/auto-prime-session-on-start.md (auto-primer doubles as a launch-time readiness check that surfaces a degenerate model state before a real query is spent)
