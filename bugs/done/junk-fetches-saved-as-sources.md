# Junk Fetches Saved as Sources

**Status:** Closed (resolved, verified by code inspection 2026-08-08)
**Type:** Bug
**Source:** Spec backlog item 4

## Summary
Fetches under ~200 chars (37-byte/4-byte stubs) were written as real .md sources, polluting the workspace with meaningless files that downstream stages treated as valid references.

## Resolution
Fixed by commit d5b8f64 (2026-07-20): `_MIN_CONTENT_CHARS = 200` in `src/tools/web.py`. Verified present and correctly positioned on 2026-08-08 (branch bug-triage, head acd706c):

- Constant defined at line 48.
- Gate at lines 326-329, inside `fetch_url_to_workspace`.
- Ordering is what makes it robust: the check runs AFTER `_strip_image_markdown` and BEFORE the provenance note is prepended, so an image-only page that cleans down to nothing cannot be padded past the threshold by the note's own characters.
- It also precedes the content-hash dedup registration, so a rejected stub never enters `_fetched_hashes` and cannot later be reported as a DUPLICATE CONTENT match.
- On rejection it returns a "TOO SHORT" message naming the character count and instructing the agent to find a different source, rather than writing the file.

## Why closed without a live firing
The previous status held this open awaiting observation of the gate firing on a live run. That is not obtainable on demand — it requires a run that happens to fetch a stub page. Session c50a227a (2026-08-08, 2-entity query) made 6 fetches, none of which triggered it, which is equally consistent with the gate working and with no junk being encountered. The code path is short, unconditional for string content, and verified by inspection, so the bug is closed rather than tracked indefinitely.

## Related
- Spec backlog item 4
- `bugs/long-junk-pages-pass-filters.md` — the complementary case (long pages that are junk), which a length floor cannot catch and which remains open.
