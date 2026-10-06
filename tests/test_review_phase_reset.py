"""
Regression tests for bugs/tui-module-state-leaks-across-runs.md defect 1:
review_phase_ctx was set True when review was enforced (tui.py) and never
reset, so after the first review round the web_calls reserve stayed released
for the rest of the process (core.py:36 releases it whenever the flag is set).

The behavioural test pins the helper; the structural tests pin the WIRING -
both turn-end paths (TUI run_agent wrapper, headless run_cli finally) must
reset the flag in a finally, so an early return, exception or quota abort
still clears it.
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tools.core import review_phase_ctx, end_review_phase

TUI = Path(__file__).parent.parent / "src" / "engine" / "tui.py"


def test_default_is_false():
    assert review_phase_ctx.get() is False


def test_end_review_phase_returns_flag_to_false():
    review_phase_ctx.set(True)
    assert review_phase_ctx.get() is True
    end_review_phase()
    assert review_phase_ctx.get() is False


def test_end_review_phase_is_idempotent():
    end_review_phase()
    end_review_phase()
    assert review_phase_ctx.get() is False


def _funcs(tree):
    return [n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _calls_end_review_phase(node):
    return any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "end_review_phase"
        for n in ast.walk(node)
    )


def test_run_agent_wrapper_resets_in_finally():
    """TUI path: run_agent must be a wrapper whose finally clears the flag
    (the body may exit via return, exception or quota-abort break)."""
    tree = ast.parse(TUI.read_text(encoding="utf-8"))
    run_agent = next(n for n in _funcs(tree) if n.name == "run_agent")
    tries = [st for st in ast.walk(run_agent) if isinstance(st, ast.Try)]
    assert any(_calls_end_review_phase(t) for tr in tries for t in tr.finalbody), \
        "run_agent does not reset review_phase_ctx in a finally"


def test_run_cli_finally_resets():
    """Headless path: run_cli already resets session_dir_ctx in its finally;
    it must reset review_phase_ctx there too."""
    tree = ast.parse(TUI.read_text(encoding="utf-8"))
    run_cli = next(n for n in _funcs(tree) if n.name == "run_cli")
    tries = [st for st in ast.walk(run_cli) if isinstance(st, ast.Try)]
    assert any(_calls_end_review_phase(t) for tr in tries for t in tr.finalbody), \
        "run_cli does not reset review_phase_ctx in its finally"


def test_review_phase_set_sites_are_two():
    """The enforcement sites are exactly two (TUI + headless). If a third
    appears, the wiring tests above must be extended to cover it."""
    tree = ast.parse(TUI.read_text(encoding="utf-8"))
    sites = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "set"
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "review_phase_ctx"
    ]
    assert len(sites) == 2, f"expected 2 review_phase_ctx.set sites, found {len(sites)}"
