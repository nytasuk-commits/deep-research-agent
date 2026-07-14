import contextvars
import functools
import asyncio

# --- TOOL QUOTA SYSTEM ---
# Protects local LLM workflows from infinite retry loops (e.g., repeatedly failing to parse a URL)
tool_quotas_ctx = contextvars.ContextVar('tool_quotas', default=None)
review_phase_ctx = contextvars.ContextVar('review_phase', default=False)

class QuotaAbortException(BaseException):
    """Raised when a tool is called repeatedly despite being over quota, indicating an LLM loop."""
    pass

def check_quota(tool_name: str) -> str | None:
    """Check if the specific tool has exceeded its per-invocation quota."""
    ctx = tool_quotas_ctx.get()
    if ctx and tool_name in ctx:
        effective_limit = ctx[tool_name]["limit"]
        reserve = ctx[tool_name].get("rules", {}).get("reserve", 0)
        if reserve and not review_phase_ctx.get():
            effective_limit = max(0, effective_limit - reserve)
            if ctx[tool_name]["used"] >= effective_limit and ctx[tool_name]["used"] < ctx[tool_name]["limit"]:
                ctx[tool_name]["used"] += 1
                return (
                    f"Error: Initial-research quota reached for '{tool_name}' "
                    f"({effective_limit} of {ctx[tool_name]['limit']} total; the remaining {reserve} "
                    f"are reserved for post-review fixes). Do NOT retry. Summarize your findings and proceed."
                )
        if ctx[tool_name]["used"] >= ctx[tool_name]["limit"]:
            ctx[tool_name]["used"] += 1
            if ctx[tool_name]["used"] > ctx[tool_name]["limit"] + 10:
                raise QuotaAbortException(f"Agent trapped in loop. Quota exceeded multiple times for {tool_name}.")
            return (
                f"Error: Quota reached. You have used the '{tool_name}' tool "
                f"{ctx[tool_name]['limit']} times out of your limit. "
                f"You MUST summarize what you've done and state clearly that you "
                f"had to stop due to quota limits."
            )
        ctx[tool_name]["used"] += 1
    return None

def _get_tool_rule(tool_name: str, rule_key: str, default_val: int) -> int:
    """Extract custom quota rules (like max_lines) for a specific tool."""
    ctx = tool_quotas_ctx.get()
    if ctx and tool_name in ctx and "rules" in ctx[tool_name]:
        return ctx[tool_name]["rules"].get(rule_key, default_val)
    return default_val

def with_quota(func):
    """Decorator to enforce quotas dynamically based on the function's name and surface full diagnostic tracebacks safely."""
    import traceback
    if asyncio.iscoroutinefunction(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if err := check_quota(func.__name__): return err
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                return f"CRITICAL TOOL EXECUTION ERROR: {func.__name__} failed internally.\n\nException Details:\n{traceback.format_exc()}"
        return async_wrapper
    else:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            if err := check_quota(func.__name__): return err
            try:
                return func(*args, **kwargs)
            except Exception as e:
                return f"CRITICAL TOOL EXECUTION ERROR: {func.__name__} failed internally.\n\nException Details:\n{traceback.format_exc()}"
        return sync_wrapper
