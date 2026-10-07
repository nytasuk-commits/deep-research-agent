"""AST guards for the tui.py -> session_log.py extraction (defect 3).

Ownership discipline: tui.py must never reference the migrated globals;
session_log.py holds exactly one module-level mutable assignment
(_session_state); the /new, /resume and turn-start boundaries call the
swap helpers by name.
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

ROOT = Path(__file__).parent.parent
TUI = ROOT / "src" / "engine" / "tui.py"
SESSION_LOG = ROOT / "src" / "engine" / "session_log.py"

MIGRATED = {"_session_events", "_current_call_by_source",
            "_current_text_by_source", "_current_session_id"}


def _tui_tree():
    return ast.parse(TUI.read_text(encoding="utf-8"))


def _func(tree, name):
    return next(n for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == name)


def _called_names(fn):
    return {n.func.id for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def test_tui_never_references_the_migrated_globals():
    for node in ast.walk(_tui_tree()):
        if isinstance(node, ast.Name):
            assert node.id not in MIGRATED, f"tui.py still references {node.id}"
        if isinstance(node, ast.Global):
            assert not MIGRATED & set(node.names), "tui.py still declares migrated globals"


def test_session_log_has_exactly_one_module_level_mutable_assignment():
    tree = ast.parse(SESSION_LOG.read_text(encoding="utf-8"))
    targets = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets.extend(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets.append(node.target.id)
    assert targets == ["_session_state"]


def test_boundaries_call_the_swap_helpers():
    tree = _tui_tree()
    assert "new_session" in _called_names(_func(tree, "on_input_submitted"))
    assert "load_session" in _called_names(_func(tree, "_load_session_by_id"))
    assert "load_session" in _called_names(_func(tree, "run_cli"))
    assert "begin_turn" in _called_names(_func(tree, "run_agent"))
