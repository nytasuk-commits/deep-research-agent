# Reviewer overrides fetched sources with its own world knowledge

**Status:** Closed (fixed by 042e946, confirmed 2026-08-08)
**Severity:** High — a false violation degraded a correct report
**First observed:** session_7c1bcadc (2026-08-03), on main at 5265201
**Introduced by:** `8b6ce76` (Reviewer given `list_workspace_files`)

## Symptom

The Reviewer reported real, correctly-fetched source data as fabricated, and the
Orchestrator removed it from the report in response. Report quality went DOWN as
a direct result of a review round.

## Evidence

The Reviewer returned:

> **Rule #1 & #4 - Invented values / Unsourced data**: The report lists numerous
> specific movie titles [...] that are fictional/fake films: "Spider-Man: Brand
> New Day", "Toy Story 5", "Minions & Monsters"/"Minions 3", "Evil Dead Burn",
> [...] These are presented as real cinema releases driving footfall but are
> invented titles that don't exist in reality.

and escalated to attacking the sources themselves:

> **Rule #4**: The report cites "Vue Gateshead Official - What's On" and
> "Kinoafisha Vue Gateshead Schedule" as sources [...] but these sources
> themselves contain fictional movie titles that are not real films.

Those titles ARE in the fetched source. `vue_gateshead_whats_on.md` contains:
Minions & Monsters
Spider-Man: Brand New Day
The Odyssey

Real Vue URL paths, from the official Vue Gateshead listings page.

## Consequence

The Orchestrator partly accepted the false violation. The final forecast table
replaced specific film titles with placeholders — "New releases ongoing", "Mixed
releases", "New release: Concert event" — and added a note saying specific titles
"cannot be verified". The draft was more useful than the reviewed version.

## Root cause

`8b6ce76` gave the Reviewer `list_workspace_files`, which let it discover and read
source files for the first time. That change is a clear net win (it produced two
correct, valuable corrections in `session_7e3c3426`). But it also created a new
conflict: when a fetched source disagrees with the model's training data, the
Reviewer trusts itself over the source.

This is the exact behaviour the prompt already forbids — `prompts.py` line 357:
"you have no web access and must not add new facts" — but that line was written
when the Reviewer could only see the report. It reads as a prohibition on
inventing facts, not as an instruction to defer to a fetched source over its own
priors.

The model's priors are also systematically wrong here: the system date is
2026-08-03 and the model's knowledge cutoff predates the films in question, so
titles that genuinely exist in 2026 look invented to it.

## Candidate fix (undecided)

A source-precedence rule: a claim traceable to a fetched source file is NOT a
violation on grounds of implausibility, regardless of what the Reviewer believes
about the world. The Reviewer may flag that a source is low-trust or that a claim
is unsourced; it may NOT flag a sourced claim as invented.

Caveat from `session_5091cd9a`: adding a large prose block to the Reviewer's Role
section degraded its output format and it ignored the added guidance entirely.
Any fix here should be as small as possible, and preferably placed in the existing
numbered checklist rather than as new prose in the Role section.

## Resolution (2026-08-08)

Fixed by `042e946` ("Reviewer rule 8: a sourced claim is not invented"), merged to main in PR #11 at `084d648` — i.e. after this bug was observed on main at `5265201`.

The committed rule is the candidate fix from this file, implemented as specified and placed in the numbered checklist rather than as Role-section prose, honouring the `session_5091cd9a` caveat:

> **Source precedence — a sourced claim is NOT invented**: If a claim can be traced to a fetched source file in the workspace, you MUST NOT flag it as invented, fictional, or implausible, however unfamiliar it looks to you. Your own knowledge has a cutoff and today's date is later than it; names, titles, products and events that genuinely exist now will look made up to you. The fetched source is the authority, not your recollection. You may flag that a claim has NO source, or that its source is low-trust — you may NOT flag a sourced claim as fabricated, and you may NEVER claim that a fetched source file itself contains invented content.

It addresses both halves of the failure: the general precedence problem, and the specific knowledge-cutoff reasoning this file identified as root cause. The final clause also closes the escalation seen here, where the Reviewer moved from doubting a claim to asserting the source file itself contained fiction.

Verified present in `src/prompts.py` as Reviewer rule 8 on 2026-08-08 (branch bug-triage), by full read of the file rather than a grep.

**Live confirmation:** session `c50a227a` (2026-08-08) — the Reviewer returned five substantive violations against a report whose figures were all traceable to fetched sources, and none was a fabrication or implausibility claim against a sourced value. Its objections were about missing date markers and unsourced derived figures, which rule 8 explicitly still permits. The Orchestrator applied the fixes by editing report text only, so no correct sourced data was removed — the specific harm recorded in this bug did not recur.

One item from the original report remains true and is NOT resolved by this fix: the Reviewer's output format still does not reliably match the required numbered list. That is a formatting issue, not a correctness one, and is out of scope here.

## Related

- `8b6ce76` — the change that enabled source reading (net positive; do not revert)
- `bugs/reviewer-passes-without-catching-errors.md` — the opposite failure mode
- `session_7e3c3426` — the same capability working correctly, for contrast
- Reviewer output format has never matched the required numbered list across
  eight observed runs
