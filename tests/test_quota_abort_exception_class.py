"""
Tests for bugs/quota-abort-exception-inherits-baseexception.md.

Corrected diagnosis (2026-10-06, framework audit): the BaseException base is
LOAD-BEARING, not a convention inversion. agent-framework 1.12.1 wraps every
tool invocation in _auto_invoke_function with:

    except UserInputRequiredException: raise
    except Exception as exc: return Content.from_function_result("Error: Function failed.")

(_tools.py:1537 direct path, :1613 middleware path). Any Exception raised by a
tool is converted into an error RESULT handed back to the model. A quota abort
made of Exception would be swallowed there, the model would see "Function
failed" and keep looping — the exact failure the loop breaker exists to stop.
BaseException is how the abort escapes the framework and reaches the salvage
catches (tui.py run loop, orchestrator.py delegation).

What IS a defect: the headless path (run_cli) detects the abort with a
string-name check (type(e).__name__ == "QuotaAbortException") despite the
class being imported at tui.py:21. Pinned here: catch by type, never by name.
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tools.core import QuotaAbortException

TUI = Path(__file__).parent.parent / "src" / "engine" / "tui.py"


def test_base_exception_base_is_pinned():
    """Regression pin for the framework finding: making this an Exception
    subclass would let agent-framework's tool-invocation handler convert the
    abort into an error result and silently disable the loop breaker.
    If the framework ever stops swallowing Exceptions from tools, revisit."""
    assert issubclass(QuotaAbortException, BaseException)
    assert not issubclass(QuotaAbortException, Exception), (
        "QuotaAbortException must NOT be an Exception subclass while "
        "agent-framework's _auto_invoke_function converts any Exception from a "
        "tool into an 'Error: Function failed.' result (_tools.py:1537/:1613)."
    )


def test_no_string_name_check_anywhere():
    """The smell the bug actually documents: detection by class-name string.
    The class is imported; catch it by type."""
    src = TUI.read_text(encoding="utf-8")
    assert '__name__ == "QuotaAbortException"' not in src, (
        "tui.py still detects the abort by string-name instead of by type"
    )


def test_run_cli_catches_quota_abort_by_type():
    """The headless except block must catch QuotaAbortException explicitly."""
    tree = ast.parse(TUI.read_text(encoding="utf-8"))
    run_cli = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "run_cli"
    )
    caught = [
        h.type.id
        for h in ast.walk(run_cli)
        if isinstance(h, ast.ExceptHandler) and isinstance(h.type, ast.Name)
    ]
    assert "QuotaAbortException" in caught, (
        "run_cli must catch QuotaAbortException by type"
    )
