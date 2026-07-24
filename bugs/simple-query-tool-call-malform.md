# Simple/Ambiguous Queries Malform Tool Calls

**Status:** Open
**Type:** Bug
**Source:** Observed in run

## Summary
Bare queries like "Compare X and Y" cause the model to emit tool calls in `<parameter=...>/` XML dialect and stall; well-framed research queries work.

## Detail
The root cause is not prompt ambiguity but a streaming-specific bug in LM Studio's chat template handling. The qwen3-coder-next chat template in LM Studio defines tool calls in Qwen's XML dialect:

```xml
<tool_call>
  <name>function_name</name>
  <parameter=arg_name>value</parameter>
</tool_call>
```

The model emits exactly this format as instructed by its chat template. When the request is **non-streaming**, LM Studio parses this XML back into structured OpenAI tool_calls correctly (verified via direct API probes — clean structured calls every time). When the request is **streaming** (`stream=True`), LM Studio does NOT reassemble the multi-line XML from the token stream — it passes the raw tokens through as content, so the client never receives a structured tool call and the run hard-stops.

## Root cause (confirmed)
Evidence: A streaming probe against LM Studio showed the tool call arriving purely as content tokens (`[CONTENT] 'think' '_tool' '>' '<parameter' '=' 'reflection' ...`) with no `tool_calls` deltas. The identical request non-streamed returned a clean structured `tool_calls` object.

### Ruled out (previously suspected, all disproven)
- **Corrupted venv**: Rebuilt from scratch, bug still occurred
- **Checklist/loop-breaker code**: Bisected to pre-session commits (still occurred)
- **enable_thinking setting**: Set true, bug still occurred — and LM Studio's Reasoning Parsing panel confirms this template does not expose Enable Thinking
- **Prompt length/query phrasing**: Probes with the full Orchestrator prompt and both simple and complex queries worked when non-streamed

The single determining variable is `stream: true`. Streaming causes the XML to leak through as raw text; non-streaming allows LM Studio's parser to reassemble it into structured data.

### Why "simple queries" seemed to be the trigger
Streaming tool-call malformation is intermittent. Complex research queries sometimes pushed the model firmly into tool-emitting behaviour that happened to parse, while simple queries reliably exposed the streaming parse failure. The real variable is **streaming**, not query complexity — the earlier "complexity theory" correctly identified a correlation but misidentified the mechanism.

### LM Studio note
Version 0.4.19 (Build 2), latest. There is no tool-call parser setting in Load or Inference tabs; LM Studio derives tool-call parsing entirely from the chat template. So the behaviour cannot be fixed via a settings toggle.

## Workaround (candidate, unverified)
Sending a throwaway first message (e.g. "create") before the real query appears to avoid the malform: the real query then lands as the model's second turn rather than a cold first turn, and the model opens with prose before emitting tool calls, which streams cleanly. Observed working 2/2 times so far — NOT yet verified across enough runs to confirm reliability (the streaming leak is intermittent). Mechanism suggests a possible cheap fix: inject a silent priming exchange before the user's first query. Use for small debug/test runs until confirmed or a real fix (Path A/B) lands.

## Suspected fix
Two viable paths:

### Path A (LM Studio-side, keeps streaming, no app changes)
Replace the model's chat template with one whose tool-call format LM Studio reassembles correctly during streaming (e.g. a Hermes-style or native tool-call template), or use a different GGUF whose bundled template streams tool calls parseably.

**Pros:** Keeps streaming behavior (TUI responsiveness)
**Cons:** Requires sourcing/editing a correct Jinja chat template; risk of breaking tool-calling while iterating

### Path B (app-side)
Make the app request non-streaming (`stream=False`) for the TUI run loop. Proven to yield clean structured tool calls, but requires reworking `handle_agent_update` in `src/engine/tui.py` to consume a single non-streamed response instead of an async update stream.

**Pros:** Direct fix; no template changes needed
**Cons:** A naive one-line `stream=False` flip hung the TUI — the loop's `async for` can't consume the non-streamed return; requires real consumption-code changes

## Related
- src/prompts.py ORCHESTRATOR_INSTRUCTIONS
- src/engine/tui.py (run_agent, handle_agent_update)
- LM Studio chat template configuration
