"""
Regression tests for bugs/web-search-skips-quota-wrapper.md.

web_search was decorated with @tool only and hand-rolled check_quota("web_search"),
so it got the counter but not the two protections @with_quota adds (core.py:193):
  - _check_repeat loop detection (identical-call and windowed alternating patterns)
  - the CRITICAL TOOL EXECUTION ERROR wrapper

fetch_url_to_workspace (web.py:122-123) already uses the @tool + @with_quota stack;
web_search must match it. Repo precedent (bugs/done/quota-exhaustion): a helper
inserted BETWEEN @tool and @with_quota silently disabled the quota path, so the
decorator stack is pinned by AST, not just behaviour.
"""

import ast
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

WEB = Path(__file__).parent.parent / "src" / "tools" / "web.py"


def _fake_client():
    client = MagicMock()
    client.text.return_value = [
        {"href": "https://example.com/a", "title": "A", "body": "snippet a"}
    ]
    client.news.return_value = []
    return client


def _quota_ctx(limit=100, used=0):
    return {"web_calls": {"limit": limit, "used": used}}


# --- AST wiring guards (the incident precedent) ---

def test_web_search_decorator_stack_is_tool_then_with_quota():
    tree = ast.parse(WEB.read_text(encoding="utf-8"))
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "web_search"
    )
    names = [
        d.id if isinstance(d, ast.Name) else getattr(d.func, "id", None)
        for d in fn.decorator_list
    ]
    assert names == ["tool", "with_quota"], (
        f"web_search decorators must be exactly @tool (outermost) then @with_quota "
        f"(directly on the function); got {names}"
    )


def test_manual_check_quota_call_removed():
    """The decorator's check_quota replaces the manual one; keeping both would
    double-count the web_calls pool."""
    tree = ast.parse(WEB.read_text(encoding="utf-8"))
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "web_search"
    )
    calls = [
        n.func.id for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    ]
    assert "check_quota" not in calls, (
        "web_search body still calls check_quota manually — remove it, @with_quota "
        "charges the pool once"
    )


# --- Behaviour: the two protections the manual path skipped ---

@pytest.mark.asyncio
async def test_identical_consecutive_search_hits_loop_detector():
    """The missing protection: two identical consecutive searches must trip
    _check_repeat (QuotaAbortException), not silently re-run the query."""
    import tools.core as core
    import tools.web as web

    web._consecutive_search_failures = 0
    web._next_allowed_search = 0.0
    token = core.tool_quotas_ctx.set(_quota_ctx())
    try:
        with patch("tools.web.get_ddgs_client", return_value=_fake_client()):
            await web.web_search("same query", max_results=5)
            with pytest.raises(core.QuotaAbortException):
                await web.web_search("same query", max_results=5)
    finally:
        core.tool_quotas_ctx.reset(token)


@pytest.mark.asyncio
async def test_different_queries_are_not_flagged_as_loops():
    """Guard against over-aggression: distinct queries must both run."""
    import tools.core as core
    import tools.web as web

    web._consecutive_search_failures = 0
    web._next_allowed_search = 0.0
    token = core.tool_quotas_ctx.set(_quota_ctx())
    try:
        with patch("tools.web.get_ddgs_client", return_value=_fake_client()):
            r1 = await web.web_search("first query", max_results=5)
            r2 = await web.web_search("second query", max_results=5)
    finally:
        core.tool_quotas_ctx.reset(token)
    assert "Found 1 result" in r1
    assert "Found 1 result" in r2


@pytest.mark.asyncio
async def test_exhausted_pool_returns_quota_error_without_calling_provider():
    """Regression pin: the decorator's check_quota must preserve the manual
    path's behaviour — error string, provider never touched, pool charged once."""
    import tools.core as core
    import tools.web as web

    web._consecutive_search_failures = 0
    web._next_allowed_search = 0.0
    ctx = _quota_ctx(limit=3, used=3)
    token = core.tool_quotas_ctx.set(ctx)
    client = _fake_client()
    try:
        with patch("tools.web.get_ddgs_client", return_value=client):
            result = await web.web_search("blocked query", max_results=5)
    finally:
        core.tool_quotas_ctx.reset(token)
    assert "Quota reached" in result
    client.text.assert_not_called()
    assert ctx["web_calls"]["used"] == 4, "pool must be charged exactly once"
