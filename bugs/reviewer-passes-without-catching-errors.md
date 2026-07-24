# Reviewer Passes Without Catching Substantive Errors

**Status:** Open
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

## Related
- src/engine/tui.py
- Review stage specification
