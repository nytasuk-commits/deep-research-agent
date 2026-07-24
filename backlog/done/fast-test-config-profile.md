# Fast Test Config Profile

**Status:** Done

## Resolution
Validated on 2026-07-20: fast-test run completed in ~11 minutes (vs ~6 hours full), FAST-TEST notice fired, reduced quotas applied. Confirmed working.
**Type:** Backlog
**Source:** Development need

## Summary
Smaller quota profile for quick test iteration.

## Detail
Current configuration profiles use production-level quotas which makes testing slow and expensive. Need a dedicated "fast" or "test" profile with:
- Lower token limits
- Shorter timeouts
- Reduced model count per run
- Smaller file sets

This would enable rapid iteration during development and local testing.

## Progress
Built and committed 2026-07-19: settings.fast_test block (enabled toggle + overrides) in config, applied via _deep_merge overlay in src/config.py, with a [config] FAST-TEST MODE ACTIVE stderr notice when active. NOT yet confirmed by a live run — remains open until a fast-test run is observed completing quickly with reduced quotas.

## Related
- Config system
