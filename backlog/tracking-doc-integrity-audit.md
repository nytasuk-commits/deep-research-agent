# Tracking-doc integrity audit

**Status:** Open — five of six sub-items resolved 2026-10-06; one code decision left open
**Type:** Backlog (doc hygiene)
**Priority:** Credibility of the whole tracking system — items 1-9 of the 2026-09-07 todo are only actionable if the records can be trusted
**Derived from:** `docs/reviews/2026-09-07/todo.md` item 10

## Sub-items and outcomes (all re-verified against current code 2026-10-06)

1. **FALSE done record — RESOLVED (record corrected).** `backlog/done/phase-2-checklist-driven-gap-mop-up.md` claimed "Done — validated" but `task_records`/checklist-gate code is absent from `src/` (grep: zero matches). The Phase 2 commits were rolled back at 959165e and deliberately not re-applied. Status rewritten to "Closed — abandoned" with the false claim named.

2. **Analyzer tool-grant claim — RECORD CORRECTED, CODE DECISION OPEN.** `bugs/done/quota-exhaustion-not-fed-back-to-delegation.md` claimed the `list_workspace_files` error "should not recur" because `8b6ce76` granted the tool. The grant was lost in the rollback and never re-applied: `af18dab` is the one unapplied clean candidate in `backlog/done/reapply-after-phase-rollback.md`, and `app.py:34` shows the Analyzer without the tool. Side-note rewritten to say the error CAN recur. **Open decision:** re-apply af18dab (one-line grant in `app.py:34`) or accept recurrence. The Reviewer already has the tool (`app.py:51`).

3. **Stale blocker refs — RESOLVED.** `backlog/multi-model-agent-routing.md` was "blocked on the streaming tool-call fix prerequisite" pointing at `bugs/simple-query-tool-call-malform.md`, which is Done — closed via LM Studio 0.4.18 rollback, not Path B. Dependency re-assessed: Path B is strategic hardening, not a hard gate; item unblocked. Same stale path fixed in `backlog/done/auto-prime-session-on-start.md` (now points at `bugs/done/...`).

4. **CURRENT_ISSUES.md referenced-but-absent — RESOLVED.** Referenced by `backlog/display-token-usage-on-completion.md` (active) and two `bugs/done/` records. Reference removed from the active file; the two done records left as historical text (they describe what was true when written). Not restored — no evidence the file's content is worth reconstructing.

5. **report_draft.md doc drift — RESOLVED 2026-10-06** (see commit 21a1e20: CLAUDE.md/README.md rewritten, backlog items amended, app.py comment fixed).

6. **Resolved-but-unmarked files — RESOLVED.** `backlog/dedup-fetches.md` (code confirmed at `web.py:15-39`) and `backlog/reapply-after-phase-rollback.md` (all clean candidates applied except af18dab) moved to `backlog/done/` with dated notes.

## Remaining open item

The af18dab decision from sub-item 2. If re-granted, also re-check the Analyzer prompt for guidance on using it (the original purpose was filename recovery after garbled fetch names — the delegate-time source-file guard from the bug-triage merge may already cover that need, which is an argument for leaving the grant out).

## Related

- `docs/reviews/2026-09-07/00_full_report.md` — origin of the audit.
- `backlog/done/reapply-after-phase-rollback.md` — the rollback ledger this audit reconciles.
