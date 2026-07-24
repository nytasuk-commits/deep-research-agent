# Multi-model routing per agent/call type

**Status:** Open (future direction)
**Type:** Backlog
**Source:** Design discussion 2026-07-20.

## Summary
Route different agent roles / call types to different models — e.g. a smaller, faster model for simple high-volume Searcher/Analyzer calls, and qwen-coder-next (the strongest performer for complex research/orchestration) for planning and synthesis.

## Detail
qwen-coder-next currently outperforms all other tried models by a considerable margin on complex research queries, so it stays as the primary model for heavy roles. The opportunity is to offload simple, frequent calls to smaller/cheaper models to reduce runtime (a major pain point — full runs take ~6 hours on one model serving all roles concurrently).

## Hard dependency
The streaming tool-call fix (Path B) is a prerequisite: The confirmed tool-call malform bug (see bugs/simple-query-tool-call-malform.md) is caused by LM Studio not reassembling XML-dialect tool calls during streaming. This bites hardest on simple, frequent calls — exactly the calls that would be routed to smaller models under multi-model. Therefore:

- **Path B** (make the app's tool-call consumption non-streaming, in src/engine/tui.py) is model-agnostic — it fixes tool-call parsing for every model, so any small model plugged in works. This is the strategic prerequisite for multi-model.
- **Path A** (per-model chat-template fixes) does NOT scale to multi-model — it would require template surgery for every model added. Avoid as the multi-model foundation.

Also needed for multi-model: a per-model streaming tool-call compatibility note — which small models emit tool calls that parse correctly — becomes a real model-selection criterion once more than one model is in play. Seed it with the qwen-coder-next finding and use the streaming probe (kept on disk: probe_stream.py) as the test method.

## Progress
None yet — blocked on the streaming tool-call fix prerequisite.

## Related
- bugs/simple-query-tool-call-malform.md
- src/engine/tui.py (run_agent, handle_agent_update)
- backlog/fast-test-config-profile.md
- config api section (would need per-agent model config)
