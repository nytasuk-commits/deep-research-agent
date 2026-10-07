# Loop breaker misses sequences of *different* narrow greps

**Status:** Open
**Type:** Backlog (robustness)
**Derived from:** `docs/reviews/2026-09-07/todo.md` item 9; the live incident was recorded in `backlog/done/multi-endpoint-router.md`, never tracked separately

## Problem

The repeat detector (`core.py:61`, window `_WINDOW_SIZE = 12`, `_WINDOW_REPEAT_THRESHOLD = 4` at `:13-15`) counts how often the **same** call signature recurs within a 12-call window. It catches identical-consecutive and alternating A-B-A-B patterns, but a loop that *varies* its arguments — 12 different narrow grep patterns, each used once — scores 1 per signature and never trips.

## Evidence

A live run showed the Reviewer making **38 grep calls** by varying patterns (recorded in `multi-endpoint-router`). The Reviewer prompt now caps this at 5 greps per file (`prompts.py:396`), but a prompt cap is not enforcement — the code-level breaker is.

Verified 2026-10-06: `core.py:13-15`, `:94-100` (window signature counting).

## Fix direction

Add a per-tool call-rate signal alongside signature repetition: e.g. flag when a read-only inspection tool (`_READ_ONLY_TOOLS`, `core.py:18`) exceeds N calls against the same file within a window regardless of argument variation, or track diminishing returns (fraction of calls returning new content). Must not punish legitimate broad greps — tune against real session logs before shipping.

## Related

- `backlog/loop-breaker-validation` (done) — the original breaker's validation record.
- `bugs/quota-abort-exception-inherits-baseexception.md` — same core.py machinery.
