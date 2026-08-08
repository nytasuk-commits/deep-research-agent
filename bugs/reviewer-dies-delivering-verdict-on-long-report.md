# Reviewer dies while delivering its verdict on a long report

**Status:** Open
**Observed:** session_8313dc8f-fa04-4351-8e71-1b844d8592a1 (2026-08-08), 8-entity "definitive guide" query, 623-line final_report.md

## Symptom
The Reviewer read the whole report successfully (two paginated read_workspace_file calls, lines 1-400 and 401-623), completed its analysis, and then failed while emitting the violations list. Its final think_tool reflection at 09:57:27 contains the complete analysis, but no violations list was ever returned to the Orchestrator.

Sequence at 09:56:59-09:57:29:
- 4 consecutive think_tool calls
- 3 returned `Error: Argument parsing failed.`
- the endpoint then returned an HTML error page instead of a completion:
  `Task failed with exception: OpenAIChatCompletionClient service failed to complete the prompt: <!DOCTYPE html>...`

## Consequence
`delegate_tasks` returned an error rather than a verdict, so the Orchestrator fell back to reviewing the report itself: it re-read final_report.md and applied its own corrections. Enforced review was effectively bypassed on the run that needed it most. The Reviewer's lost findings included:
- fictional/placeholder source URLs presented as real (hogeheer499-commits.github.io, runaihome.com, insidepc.tech)
- an implausible Kimi K2 memory figure (~5.3 GB at Q5_K_M for a 1T-parameter model)
- unsourced performance numbers and "estimated" values presented as fact
- unsourced entries in the discovery section

Because the Orchestrator self-corrected, the fabricated URLs were rewritten by the same agent that produced them, with no independent check.

## Notes
- The malform (`Argument parsing failed`) on repeated think_tool calls is the same class of failure seen previously with tool-call serialisation.
- The verdict was long: 7 violation categories across a 623-line report. Output length at the point of failure is a candidate factor.
- Two-entity queries with short reports have not reproduced this — it appears load- or length-dependent.

## Next step
Determine whether the failure is output length, consecutive think_tool calls, or an endpoint-side error, before changing the Reviewer prompt.
