# Reviewer overrides fetched sources with its own world knowledge

**Status:** Open
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

## Related

- `8b6ce76` — the change that enabled source reading (net positive; do not revert)
- `bugs/reviewer-passes-without-catching-errors.md` — the opposite failure mode
- `session_7e3c3426` — the same capability working correctly, for contrast
- Reviewer output format has never matched the required numbered list across
  eight observed runs
