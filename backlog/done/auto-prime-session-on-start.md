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

---

## RESOLVED — commit `f7e1de7`

Auto-primer implemented and validated. On session start the app sends a throwaway "Hello" as a real user turn through the full model round-trip; the injected "Hello" is suppressed from the TUI transcript while the agent's greeting is rendered, so the user sees the agent ready before typing.

**Validation:** On a fresh session the greeting appeared unprompted (no manual priming typed), and the user's subsequent first real query produced a well-formed tool-call stream. This confirms the open risk noted above — a suppressed-but-real turn DOES warm the stream the same way a visible manual turn does. All acceptance criteria met.

**Scope of closure:** This closes the WORKAROUND only. The underlying tool-call malform (Qwen XML chat template not stream-parsed by LM Studio) is NOT fixed by this item; the root fix (Path B non-streaming rework) remains open in `bugs/simple-query-tool-call-malform.md`.

**Unexpected benefit (feature, not just fix):** Because the auto-primer runs the full model round-trip on startup, the greeting doubles as a live readiness check — the pipeline self-tests on launch. If the model is unloaded, the endpoint is down, or the model is in a degenerate state (e.g. the `?`-collapse seen with bad saved settings or a broken LM Studio build), it shows up in the greeting immediately, before the user spends a real query on it. The model prompting the user is itself confirmation the stream is warm and the chain works end-to-end.
