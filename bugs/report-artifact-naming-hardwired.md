# Report Artifact Naming Is Hardwired

**Status:** Open
**Type:** Bug
**Source:** Code inspection

## Summary
final_report.md is load-bearing across the tui.py review state machine and the required_artifact config check, so it cannot be renamed piecemeal.

## Detail
The report artifact naming creates a constraint where Phase 3 must handle renaming properly because:
1. The TUI's review state machine expects specific filenames
2. Config's required_artifact check validates against hardcoded names
3. Intermediate stages may reference these paths

This hardwiring limits flexibility and makes refactoring risky without understanding all dependencies.

## Related
- src/engine/tui.py
- Config required_artifact check
