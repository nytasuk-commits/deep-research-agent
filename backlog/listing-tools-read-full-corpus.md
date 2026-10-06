# list_workspace_files reads every file's full content to compute counts

**Status:** Open
**Type:** Backlog (efficiency)
**Derived from:** `docs/reviews/2026-09-07/todo.md` item 7

## Problem

`list_workspace_files` (`fs.py:163-171`) calls `get_workspace_file_content(k)` for **every** workspace file just to compute `len(content.splitlines())` and `len(content)`. In a run with a dozen fetched sources (each 8-70 KB, e.g. `run_1791298712`: 12 files up to 71 KB), every call re-reads the full corpus. It is a quota-charged tool that agents call repeatedly, and the TUI's `/files` picker (`tui.py:1164` `_show_file_picker`) does the same full-content read for byte counts.

## Evidence

Verified 2026-10-06: `fs.py:163-171` (loop over `get_workspace_file_content`), `tui.py:1164+`.

## Fix direction

Compute counts from file metadata or a single streaming pass (line count via buffered read, size via `stat`), or cache counts per file version in the workspace layer. Distinct from `whole-file-read-throughput` (Analyzer reading *strategy*) — this is the tool's own implementation cost.

## Related

- `backlog/whole-file-read-throughput.md` — complementary, different layer.
