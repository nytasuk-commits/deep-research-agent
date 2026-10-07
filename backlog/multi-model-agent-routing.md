# Multi-model routing per agent/call type

**Status:** Open (future direction)
**Type:** Backlog
**Source:** Design discussion 2026-07-20.

## Summary
Route different agent roles / call types to different models — e.g. a smaller, faster model for simple high-volume Searcher/Analyzer calls, and qwen-coder-next (the strongest performer for complex research/orchestration) for planning and synthesis.

## Detail
qwen-coder-next currently outperforms all other tried models by a considerable margin on complex research queries, so it stays as the primary model for heavy roles. The opportunity is to offload simple, frequent calls to smaller/cheaper models to reduce runtime (a major pain point — full runs take ~6 hours on one model serving all roles concurrently).

## Dependency (re-assessed 2026-10-06 — no longer a hard blocker)
The streaming tool-call fix (Path B) was a prerequisite while the tool-call malform was an open bug. That bug (`bugs/done/simple-query-tool-call-malform.md`) is now **closed via LM Studio 0.4.18 rollback, not Path B** — Path B was never applied. So Path B is strategic hardening rather than a blocked-on-it prerequisite: still the model-agnostic foundation for plugging in unknown small models, but nothing currently observed blocks starting multi-model on the pinned LM Studio version. The bug's superseded-analysis note says to revisit Path A/B only if a streaming-specific malform recurs on a known-good version. Therefore:

- **Path B** (make the app's tool-call consumption non-streaming, in src/engine/tui.py) is model-agnostic — it fixes tool-call parsing for every model, so any small model plugged in works. This is the strategic prerequisite for multi-model.
- **Path A** (per-model chat-template fixes) does NOT scale to multi-model — it would require template surgery for every model added. Avoid as the multi-model foundation.

Also needed for multi-model: a per-model streaming tool-call compatibility note — which small models emit tool calls that parse correctly — becomes a real model-selection criterion once more than one model is in play. Seed it with the qwen-coder-next finding and use the streaming probe (kept on disk: probe_stream.py) as the test method.

## Progress
None yet. Unblocked 2026-10-06: the blocking bug closed via LM Studio rollback (see Dependency above), so the prerequisite is now a judgement call, not a hard gate.

## Related
- bugs/done/simple-query-tool-call-malform.md
- src/engine/tui.py (run_agent, handle_agent_update)
- backlog/fast-test-config-profile.md
- config api section (would need per-agent model config)
