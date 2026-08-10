# Report artifact naming is hardwired to final_report.md

**Status:** Open
**Type:** Backlog (enhancement)
**Priority:** Low — no defect; only blocks renaming the artifact, which nothing currently requires
**Source:** Code inspection; reclassified from bugs/ 2026-08-08

## Summary

`final_report.md` is load-bearing in several places, so the deliverable cannot be renamed piecemeal. This is a design constraint rather than a defect — no misbehaviour has been observed, and the fixed name is what makes the review gate and the artifact check work.

## Where the name is depended on

1. The TUI review state machine keys off the report filename to decide when review is required and when a turn may end.
2. The config `required_artifact` check validates that a deliverable exists under the expected name.
3. The Orchestrator prompt instructs writing `final_report.md` exactly once, and `report_draft.md` is the separate synthesis artifact.

## Why this is not a bug

Nothing fails. The constraint is load-bearing in the useful sense: a fixed, known filename is what allows code — rather than prompt text — to verify that a report was actually produced and reviewed. Making the name configurable would weaken that unless every consumer read the same config value.

## If it is ever changed

Any rename must land as one coordinated change across all three consumers above, plus the review-round enforcement in `tui.py` and the CLI's artifact check. A partial rename would silently break the review gate: the state machine would wait for a file that never appears, or the artifact check would pass on a stale file from a previous run. Validate on a live run that exercises at least one review round, not just by inspection.

## Related

- `src/engine/tui.py` — review enforcement and the required-artifact check
- `src/prompts.py` — Orchestrator instruction to write `final_report.md` exactly once
- Commit `ee70656` — the write-exactly-once rule that depends on the fixed name
