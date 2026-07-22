# File-Based Coverage Gate Instead of Model-Asserted JSON

**Status:** Open
**Type:** Backlog
**Source:** Design discussion

## Summary
Proposal: model writes structured coverage to a file, code gatekeeps completeness, superseding the §8a JSON self-report.

## Detail
Current approach relies on model assertions in JSON format (§8a) about coverage completeness. This is unreliable as models can hallucinate or misrepresent their actual output.

Proposed improvement:
1. Model writes structured coverage report to a file
2. Code validates that file contents match the checklist requirements
3. Code gatekeeps final acceptance based on this validation

This adds a verifiable gate between model output and final report generation.

## Related
- Spec §8a JSON self-report section
- Design discussion
