# Reviewer Passes Without Catching Substantive Errors

**Status:** Closed — cannot reproduce (2026-08-08)
**Type:** Bug
**Source:** Observed in run

## Summary
The Reviewer returned a pass despite a summary/body framing mismatch in the report.

## Detail
The review logic appears to have weak verdict logic — it's not properly validating the consistency between report sections or catching substantive structural issues like misaligned framing between summary and body content. This undermines the review stage's purpose as a quality gate.

## Suspected fix
Strengthen the Reviewer verdict logic to:
1. Compare summary and body content alignment
2. Check for framing consistency across sections
3. Fail on substantive rather than just cosmetic issues

## Closed: cannot reproduce (2026-08-08)

Two independent runs have failed to reproduce the soft pass, against a single original observation:

- `ecf57d30` — the Reviewer caught 4 substantive violations, including the bandwidth conflict.
- `c50a227a` (2026-08-08) — the Reviewer returned 5 substantive violations on a 2-entity report: undated price figures, an unsourced derived value, and speculative wording. It did not return a pass, and its objections were substantive rather than cosmetic, which is the specific failure this bug describes.

The suspected fix (explicit summary/body alignment and framing-consistency checks in the verdict logic) was never built, so the non-reproduction is not the result of any change made in response to this report. Either the original observation was a one-off, or it was incidentally addressed by the Reviewer prompt work committed since — the numbered rules 7, 8 and 9 all postdate it.

Closed rather than left downgraded because a single unreproduced observation with no code change to point at cannot be verified further. If a framing-mismatch pass appears again it will be logged as a fresh bug with a current session reference, which is more useful than reviving this one.

## Related
- src/engine/tui.py
- Review stage specification
