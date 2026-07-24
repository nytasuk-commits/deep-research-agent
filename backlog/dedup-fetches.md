# Layered fetch dedup (URL + content-hash)

**Status:** Done — pending live confirmation
**Type:** Backlog
**Source:** Runtime investigation 2026-07-20; same source was fetched ~29 times in the 8-model run.

## Summary
Avoid re-fetching a URL already fetched this run, and avoid saving content byte-identical to something already saved this run.

## Detail
fetch_url_to_workspace now does layered dedup:

1. **URL check before fetching** — if the URL was already fetched this run, returns the existing SAVED_FILENAME and skips the network fetch entirely;
2. **Content-hash check after image-strip/block-marker/too-short gates** — if the cleaned content's md5 matches something already saved this run, skips the write.

Registry is per-run (keyed by `session_dir_ctx`), concurrency-safe (`_dedup_lock`), and memory-bounded — `_dedup_reset_to_current` prunes all non-current run keys on every call, so the dicts never hold more than one run's data. Binary fetches skip hash-dedup (md5 only computed for string content) but still get URL-dedup.

## Resolution
Committed 2026-07-20. Verified by inspection (including a fix for a binary-path NameError). NOT yet observed firing on a live run — confirm on next complex run (which re-fetches popular sources) that "ALREADY FETCHED" / "DUPLICATE CONTENT" messages appear and duplicate files drop.

## Scope note
This is byte/URL dedup only (the modest lever). The larger inefficiency — 8 tasks independently converging on the same source even when content differs slightly (search overlap) — is separate and unaddressed; see backlog/whole-file-read-throughput.md item 3b.
