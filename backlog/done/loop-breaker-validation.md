# Loop-Breaker Validation

**Status:** Done
**Type:** Backlog
**Source:** Uncommitted fix in src/tools/core.py

## Resolution
Validated firing on the 2026-07-19 8-model run (56 firings across 4 agents incl. nested Analyzers). Fix committed.

## Summary
_loop_breaker validation complete. Fix confirmed working but not yet committed.

## Detail
A fix for the loop breaker mechanism exists in src/tools/core.py but:
1. Is not committed to git
2. Hasn't been validated to fire correctly on a clean run

**Confirmed firing on the 2026-07-19 8-model run:** 56 firings across 4 agents including nested Analyzers (26 each on two image-heavy-page Analyzers). Fix works. Caveat: it returns an error rather than hard-stopping, so agents can resume flailing via slightly-varied calls — the underlying image-markdown-drowns-grep bug (see bugs/) remains the real fix.

This represents technical debt and potential runtime issue.

## Action needed
Commit the change to git.

## Related
- src/tools/core.py _loop_breaker function
- Bug: image-markdown-drowns-grep (the underlying root cause)
