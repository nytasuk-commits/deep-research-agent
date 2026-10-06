# Session persistence rewrites the whole JSON per event (quadratic I/O)

**Status:** Open
**Type:** Backlog (performance + correctness)
**Priority:** Highest code item in the 2026-09-07 review
**Derived from:** `docs/reviews/2026-09-07/todo.md` item 6

## Problem

`_write_log()` (`tui.py:31-57`) serialises and rewrites the **entire** session JSON on every call, and it is called from the per-event logging path (`tui.py:69`, `:148` — every streamed text/reasoning chunk and tool event), plus `/persistence` toggle (`:587`), turn finalisation (`:1025`, `:1043`) and headless end (`:1504`). A run with N events therefore writes O(N) full snapshots of O(N)-growing files: **O(N²) disk I/O** over a long run. Sessions feed `/resume` and the eval harness, so long runs pay it repeatedly.

## Bundled correctness item

Five `open()` calls on session JSON omit `encoding="utf-8"`: `tui.py:603`, `:646`, `:1198`, `:1327`, `:1548`. On Windows these default to the ANSI codepage (cp1252), so a session containing non-cp1252 characters can be **corrupted on read** (or written unreadably). The write side (`:54`) already passes `encoding="utf-8"`; the read side does not. (The 2026-09-07 review counted four; `:646` is a fifth, verified 2026-10-06.)

## Fix direction

Debounce the per-event writes (write on a timer or every K events, always write at turn end and on abort), or append JSONL and compact on read. Add `encoding="utf-8"` to all five read sites. Validate: a long run's session file stays valid and `/resume` reconstructs it; a session with unicode (e.g. en-dash figures from reports) round-trips on Windows.

## Related

- `backlog/listing-tools-read-full-corpus.md` — the other full-corpus I/O hot spot.
