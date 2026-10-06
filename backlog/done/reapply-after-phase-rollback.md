# Re-apply candidates after Phase 2/3 rollback (FOR REVIEW)

Context: branch reverted to commit 959165e (pre–Phase 2/3) because the phased
draft/corrective model was unstable. The commits below were made AFTER 959165e on
`david-refinements` and are independent of the rolled-back phases. Review and apply individually;
confirm each is genuinely absent before applying (`git show <hash> --stat`).

## Clean candidates (no phase dependency)
- d5b8f64 — reject fetches under 200 chars as junk
- a958662 — 60s hard wall-clock ceiling on fetches (byte-trickle timeout defeat)
- 4108d3c — reject 429/rate-limit pages, 429 backoff-retry, explicit SAVED_FILENAME
- cd95374 — Amazon "continue shopping" interstitial in _block_markers (APPLIED manually already — verify before re-picking)
- 1751454 — strip image-markdown to de-noise Analyzer grep
- 8c87bcc — layered fetch dedup (URL + content-hash), skip hash-dedup for binary
- cffd326 — dedup backlog documentation companion to 8c87bcc
- 9ce929e — identical-consecutive-call loop breaker in with_quota
- 6ea3611 — loop-breaker validation note
- d848c89 — truststore dependency fix (required by tools/web.py)
- f974897 — stop orphaned tool-call spinners when a sub-agent ends
- 3215e21 — widen quota loop-kill threshold +3 -> +10
- 0ce3c13 — client read timeout (300s) + salvage workspace files on quota abort
- d26993d — raise LLM client timeout to 1800s via pre-built AsyncOpenAI
- 9500a70 — raise LLM client read timeout to 1800s (companion to d26993d)
- af18dab — give Analyzer list_workspace_files for filename recovery
- 851a88a — remove scratch diagnostic probes from tracking; gitignore them
- 91d0903 — ignore .claude/ working directory

## Needs a judgement call before applying (may touch phase/synthesis flow)
- f1e37e9 — coverage + grounding: one task per named entity, synthesis guard,
  exact-filename handoff, Analyzer fallback on filename miss. Mostly independent,
  but "synthesis guard" may touch report flow — inspect first.
- 87f927c — source-reconciliation rule in orchestrator synthesis. Independent in
  principle, but backlog noted it never confirmed firing — inspect first.

## Deliberately NOT re-applying (the rolled-back phases)
Phase 3: 58cbfb1, 9429dbb, 9f45bbe, d4ea2de
Phase 2: bbd3d0a, f8ac808, 5de2bb1, 91a4123, a3004d6
Checklist Build Step 1: 9ef21c0, 706ce28, 4ba4648, b253b4d, 81b8eaa
Budget allocation/rollover/unified web_calls: 0e97152, 9762031, 11029f1, d99e679,
  4eec355, 7139210, 21824fe, ff0ebd2
Phase/budget spec docs: 27332dc, 9495c85, 463f854

Note: some "clean candidate" fixes may have been authored on top of phase code and
could carry small conflicts when cherry-picked; resolve per-commit.
