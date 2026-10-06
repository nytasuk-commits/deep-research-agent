"""
Unit tests for engine.orchestrator._coerce_task_list and the delegate_tasks
decorator integrity.

This is the fix for bugs/delegate-tasks-accepts-string-not-list: models in this
stack (Qwen XML template / LM Studio malformation family) sometimes deliver
`tasks` as a JSON string instead of a list of dicts. Without coercion,
len(tasks) counts characters, iteration yields single characters, and the agent
receives a CRITICAL traceback string instead of either a working delegation or
an actionable error.

The AST test guards the decorator binding: bugs/done/quota-exhaustion-not-fed-
back-to-delegation.md records a helper inserted BETWEEN @tool and @with_quota
and delegate_tasks, which silently registered the helper as the tool and lost
the quota wrapper - ast.parse succeeded and the suite stayed green. The walk
below makes that failure mode loud.
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.orchestrator import _coerce_task_list

SRC = Path(__file__).parent.parent / "src" / "engine" / "orchestrator.py"


def _task(name="T1", agent="Searcher"):
    return {"task_name": name, "instructions": "do it", "agent_id": agent}


def test_list_of_dicts_passes_through_unchanged():
    tasks = [_task()]
    result, err = _coerce_task_list(tasks)
    assert err is None
    assert result == tasks


def test_json_string_list_is_parsed():
    import json
    result, err = _coerce_task_list(json.dumps([_task(), _task("T2")]))
    assert err is None
    assert result == [_task(), _task("T2")]


def test_json_string_single_dict_becomes_one_task_list():
    import json
    result, err = _coerce_task_list(json.dumps(_task()))
    assert err is None
    assert result == [_task()]


def test_bare_dict_becomes_one_task_list():
    result, err = _coerce_task_list(_task())
    assert err is None
    assert result == [_task()]


def test_non_json_string_returns_actionable_error_not_traceback():
    result, err = _coerce_task_list("Review final_report.md and fix violations " * 20)
    assert result is None
    assert err is not None
    assert "list of task" in err
    assert "Traceback" not in err


def test_json_string_of_scalar_returns_error():
    result, err = _coerce_task_list("42")
    assert result is None
    assert err is not None


def test_list_with_non_dict_entry_returns_error():
    result, err = _coerce_task_list([_task(), "just a string task"])
    assert result is None
    assert err is not None
    assert "task_name" in err


def test_empty_list_passes_through():
    # Empty list is the caller's problem downstream, not a coercion error.
    result, err = _coerce_task_list([])
    assert err is None
    assert result == []


def test_delegate_tasks_keeps_tool_and_with_quota_decorators():
    """AST walk: delegate_tasks must still carry BOTH @tool and @with_quota
    directly on it (see module docstring for the incident this guards)."""
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "delegate_tasks"
    )
    deco_names = set()
    for d in fn.decorator_list:
        if isinstance(d, ast.Name):
            deco_names.add(d.id)
        elif isinstance(d, ast.Call) and isinstance(d.func, ast.Name):
            deco_names.add(d.func.id)
    assert "tool" in deco_names, "delegate_tasks lost its @tool decorator"
    assert "with_quota" in deco_names, "delegate_tasks lost its @with_quota quota wrapper"
