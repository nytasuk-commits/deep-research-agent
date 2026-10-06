# delegate_tasks accepts `tasks` as a string with no coercion or validation

**Status:** Fixed 2026-10-06 — `_coerce_task_list` at orchestrator.py module level, called at the top of `delegate_tasks`; pinned by `tests/test_delegate_tasks_coercion.py` (9 cases incl. an AST walk that keeps `@tool`/`@with_quota` bound to the real function). NOT yet validated on a live run — the malformed call must recur organically to confirm the error string reaches the agent.
**Severity:** High — the tool-call malformation family (Qwen XML template, LM Studio) repeatedly delivers `tasks` as a JSON string; without coercion the call degrades into a confusing traceback instead of either working or failing with an actionable error
**Derived from:** `docs/reviews/2026-09-07/todo.md` item 2; first flagged (untracked) in `bugs/done/web-call-quota-exhausted-on-multi-entity-queries.md`

## Symptom

A live `delegate_tasks` call received `tasks` as a 1052-character **string** instead of a list of dicts. The handler (`orchestrator.py:348`, `async def delegate_tasks(tasks: list[dict])`) has no coercion or validation, so the type annotation is aspirational only.

## Evidence

- The 1052-char string call recorded in `web-call-quota-exhausted-on-multi-entity-queries`.
- `tools/reviewer_verdict_sweep.py` had to add string-`tasks` handling to parse real session logs — the shape still occurs in the corpus.
- Code inspection 2026-10-06: `orchestrator.py:348-371` — `N = len(tasks)` on a string returns the **character count**, then `for idx, t in enumerate(tasks)` iterates single characters and `t.get(...)` raises `AttributeError`. The `@with_quota` wrapper (`core.py:196`) catches it and returns a `CRITICAL TOOL EXECUTION ERROR` traceback string to the agent — so the failure is neither silent nor actionable: the agent sees a Python traceback where it needs "pass a list of task dicts", and the `delegate_tasks` quota charge is spent either way.

## Root cause

No input normalisation at the tool boundary. Models in this stack emit tool arguments as strings when their tool-call serialisation partially malforms; the tool trusts the annotation.

## Fix direction

Coerce at the top of `delegate_tasks`: `json.loads` a string that parses to a list; accept a bare dict as a single-task list; return a short actionable error string (not a traceback) for anything else. Pinned by tests.

## Related

- `bugs/reviewer-output-format-non-compliance.md` — same malformation family (leaked tool-call block as verdict text).
- `bugs/done/simple-query-tool-call-malform.md` — the root template/streaming issue behind the family.
