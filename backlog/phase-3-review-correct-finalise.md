# Phase 3 — Review→Correct→Finalise Restructure + Report_Draft.md Rename

**Status:** Closed 2026-10-06 — restructure implemented; the report_draft.md rename half is abandoned by design
**Type:** Backlog
**Source:** Spec

## Summary
Phase 3 implementation: review→correct→finalise restructure plus rename final_report.md to report_draft.md.

## Outcome
The restructure half is implemented: the TUI enforces review rounds after `final_report.md` is written (`tui.py`, `max_review_rounds` default 2), the Reviewer reviews the file in place, and corrections are made by editing the existing `final_report.md` text only, with no new research during the review stage.

The rename half is **abandoned**: the draft/final split was removed from the design (2026-10-06). There is no `report_draft.md` artifact and none is planned. `final_report.md` is reviewed and corrected in place; CLAUDE.md and README.md were corrected to match on 2026-10-06.

## Detail (historical)
This phase addressed bugs 3 and 7:
- Bug 3: Review stage produces byte-identical duplicate reports (fixed by restructuring the review flow)
- Bug 7: Report artifact naming is hardwired (the rename-to-report_draft.md fix was dropped; see backlog/report-artifact-naming-hardwired.md, which now records the fixed name as the intended design)

## Related
- Bug: review-stage-duplicate-reports
- Bug: report-artifact-naming-hardwired
- Spec Phase 3 section
