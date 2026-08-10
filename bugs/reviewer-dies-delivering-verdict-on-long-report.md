# Reviewer dies while delivering its verdict on a long report

**Status:** Open - diagnosis corrected 2026-08-10; candidate fix committed but untested
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

## Diagnosis correction (2026-08-10)

Re-reading the same session log shows the framing above is wrong on two points. The bug is still open; only the explanation changes.

**This is not Reviewer-specific.** The `Argument parsing failed` to `Task failed with exception` sequence occurs **eight times** across this single run, not once at the verdict. Full counts from the log: 11 `Argument parsing failed` tool results (events 167, 559, 1014, 1264, 1330, 1381, 1491, 1519, 1569, 1570, 1571) and 8 `Task failed with exception` results (events 610, 1072, 1267, 1333, 1382, 1492, 1520, 1573). **All 8 task failures carry an HTML body.** The Reviewer's death at 1569-1573 was the eighth instance of a failure mode that had already hit seven other sub-agents in the same run - it is simply the one whose loss mattered, because a lost verdict has no salvage path whereas a failed research task degrades gracefully.

**Output length is therefore not the candidate factor.** The "Notes" section above suggests the verdict's length (7 violation categories over 623 lines) as a likely cause. The other seven failures were ordinary research and analysis tasks with no long output, so length does not explain them. The common factor across all eight is the endpoint returning an HTML error page instead of a completion.

**Consequence for the retest.** The absence of this failure on short two-entity queries, cited above as evidence of length-dependence, is better explained by exposure: 8 failures across 746 tool calls is roughly one per 93 calls, so a 40-call run would usually show none. That makes a wide run a genuinely discriminating test rather than a weak one - at ~8 occurrences per wide run, a clean wide run would be strong evidence.

**Candidate fix is committed but has never faced this.** `5f82d30` added `max_retries=3` on the AsyncOpenAI client specifically for intermittent HTML-bodied 500s, retried at the client layer so it costs no tool quota. It postdates this run: the bug was logged from this session by `66b0c8e`, and the retry commit came afterwards on `figure-date-stamps`. Since every one of the 8 failures here was HTML-bodied, the fix targets exactly the right layer and is more likely to bite than the original write-up implied.

**Next step, revised.** Run the standard wide 8-entity query on current `main` (which now contains `5f82d30`) and count `Argument parsing failed` and `Task failed with exception` in the session log. Baseline to beat: 11 and 8 respectively, with all 8 HTML-bodied. Zero task failures would close this. A reduced but non-zero count would indicate the retries help but the malform has a second cause - in which case the remaining question is why the tool-call stream malforms in the first place, which is the same Qwen-template-plus-LM-Studio stream-parsing issue documented against the priming workaround.

**Confounder introduced 2026-08-10.** Endpoint 192.168.68.61 was removed from the config after it showed session-contention symptoms (a model answering with the tool vocabulary of another session). If the HTML-bodied 500s originated disproportionately from that endpoint, its removal alone would reduce the failure count and a clean wide run would not prove max_retries=3 works. Commit 63be22b logs the endpoint URL on task failure, so the retest should record which endpoint served each failure; if none appear, re-add .61 before concluding.
