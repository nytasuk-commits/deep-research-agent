# Auto-prime session on start (workaround for manual priming prompt)

**Problem:** The first real user message to a fresh session malforms the tool-call stream (Qwen XML chat template + LM Studio not stream-parsing it), so the user must manually send a throwaway "create"/"hello" turn before their real query. Manual, easy to forget; a first real query without priming produces a broken first turn.

**Fix:** On session start, automatically send a throwaway "Hello" as the user turn, through the full model round-trip (it MUST be a real turn — that is what warms the stream; a mocked/faked reply will NOT prime it). Suppress the injected "Hello" from the TUI transcript, but DO render the agent's default greeting response, so the user sees the agent ready and waiting before they type anything.

**Acceptance:**
- User never types a priming message.
- The injected "Hello" does not appear in the TUI.
- The agent's greeting DOES appear.
- A user's first real query then produces a well-formed tool-call stream (no malform).

**Notes / risks:**
- Confirm the auto-hello actually primes (same effect as manual). If a suppressed-but-real turn does not warm the stream the way a visible one does, this does not work — verify before closing.
- Headless/runner path: decide whether it auto-primes there too, or only in the TUI.
- Keep the injected text trivial/configurable; it only needs to trigger one round-trip.

**This is a WORKAROUND, not a fix.** The underlying malform is root-caused to the Qwen XML chat template not being stream-parsed by LM Studio. The real fix is the non-streaming rework (Path B), tracked in `bugs/simple-query-tool-call-malform.md`. This item only hides the manual priming step; it does not resolve the malform.
