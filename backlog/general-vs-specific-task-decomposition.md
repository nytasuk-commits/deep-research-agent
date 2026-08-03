# Decomposition: general factor vs specific instance

**Status:** Backlog
**Priority:** High (correctness of coverage, not a crash)
**Depends on:** None
**Blocks:** None
**Evidence base:** six runs of the Gateshead footfall query, 2026-08-03

## Problem

When a query asks for both the *general mechanism* of a factor and a *specific
instance to look up*, the Orchestrator creates one task and gets only one of the
two answers. This is not tied to any one subject — it recurs across weather,
cinema releases and local events in the same query.

Worked example. The prompt asked for:
- "weather effects on UK quick-service restaurant footfall" (general mechanism)
- "the Gateshead weather forecast where available" (specific instance)

In `session_7e3c3426` the Orchestrator created a single `Weather effects
research` task. All five weather files fetched were research ABOUT weather
effects (Ariadne footfall guide, BII hospitality article, RSM tracker, Springer
study, restaurant seasonality piece). No Met Office or BBC Weather fetch was
attempted. Of 31 workspace files, zero contained a Gateshead forecast.

The downstream behaviour was CORRECT given the workspace: the Reviewer flagged
the missing forecast, and the report disclosed it honestly ("No specific
Gateshead weather forecast data is available in the research sources for this
period"). The failure is entirely at decomposition.

## Why this is not a per-subject fix

The obvious fix — a prompt rule about fetching weather forecasts — would be the
fourth query-specific accretion in the prompt set. Reviewer rule 1 already
refers to "component, platform, or chip" and "memory bandwidth, architecture,
core counts"; rule 3 to price and configuration. Those were added for the
7-model hardware comparison and contributed nothing across six footfall runs.
Adding a weather rule repeats that mistake in a new direction.

The generic statement of the defect is:

> A request naming BOTH a general factor AND a specific instance of that factor
> requires two tasks. One task answers only one of them.

That framing covers weather, cinema releases and events simultaneously.

## Capability is present but unreliable

`session_2e65dc82` DID decompose weather correctly and fetched a real BBC
forecast with per-day conditions and temperatures for all 15 forecast days, with
no special prompting. So the model can do this; it does not do it consistently.

Per-run coverage of the three specific-instance lookups the query asked for:

| Run | School term dates | Weather forecast | Local events | Report rating |
|---|---|---|---|---|
| `session_4546ccdd` | correct | not fetched | Novum Festival (Newcastle) | 7 |
| `session_2e65dc82` | self-contradictory | full per-day BBC forecast | none found | 5 |
| `session_11b66ee0` | correct | not fetched | none found | 5 |
| `session_f695b2c9` | INVERTED (claimed in term during August) | per-day conditions | one film release, miscited | 5.5 |
| `session_5091cd9a` | correct but contradicted by a stray row | not fetched | none found | not rated |
| `session_7e3c3426` | correct, arithmetic shown | not fetched | 4 dated on-site Trinity Square events | 7.5 |

No run got all three right. Each run has the pieces; none assembles them.

## Candidate directions (undecided)

1. **Orchestrator decomposition rule.** State that a general factor plus a
   named specific instance are separate tasks. Generic, cheap, and would have
   caught all three cases at once. RISK: this is a prompt rule asking the model
   to do more analysis while composing, which is the class of instruction that
   showed only partial adherence in `figure-date-stamps` and led to that branch
   being parked. Prompt rules alone have proven insufficient for behaviours the
   model finds costly.
2. **Mechanical decomposition check.** Enforce in code that each named
   specific-instance lookup produces a task. Reliable but requires parsing
   intent from the query, which is a large piece of work.
3. **Post-research coverage gate.** Compare the delegated task list against the
   original query before synthesis and flag unaddressed specifics. Related to
   the parked checklist-completeness work.

## Related

- `funnel-prompts` — same underlying theme: decomposition and synthesis
  reliability rather than any individual tool defect
- `figure-date-stamps` (parked) — precedent that prompt rules alone do not hold
  for costly behaviours
- Reviewer checklist rules 1 and 3 are hardware-query-specific and inapplicable
  to other query types; generalising them is a separate item
- Reviewer output format has never been compliant across seven observed runs
  (bulleted or narrated, never the numbered list the prompt requires)
