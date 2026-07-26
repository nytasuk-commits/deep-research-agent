# Junk Fetches Saved as Sources

**Status:** Tracking (fix committed, awaiting live confirmation)
**Type:** Bug
**Source:** Spec backlog item 4

## Summary
Fetches under ~200 chars (37-byte/4-byte stubs) get written as real .md sources.

## Detail
Very short fetch responses — essentially placeholder/stub content rather than actual useful information — are being saved to source files with the same format as legitimate research results. This pollutes the source directory with meaningless content and can confuse analysis stages that treat all .md files as valid references.

## Suspected fix
Reject short fetches by length before saving them as sources. Implement a minimum content threshold (e.g., 200 characters) for what qualifies as a valid source.

## Progress
Fix committed 2026-07-20 (commit d5b8f64): _MIN_CONTENT_CHARS = 200 gate in src/tools/web.py rejects fetches whose cleaned content (measured after image-strip, before the provenance note is added) falls below 200 chars, returning a "TOO SHORT" guidance message instead of saving. Sits alongside the existing block-marker check. Verified by inspection; NOT yet observed firing on a live run — will confirm on next run that produces a junk/stub fetch.

## Related
- Spec backlog item 4
