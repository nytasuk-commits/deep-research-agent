import contextvars
import functools
import asyncio

# --- TOOL QUOTA SYSTEM ---
# Protects local LLM workflows from infinite retry loops (e.g., repeatedly failing to parse a URL)
tool_quotas_ctx = contextvars.ContextVar('tool_quotas', default=None)
review_phase_ctx = contextvars.ContextVar('review_phase', default=False)

# Repeat detection threshold: consecutive identical calls beyond this count are refused
_REPEAT_THRESHOLD = 1

_QUOTA_ALIASES = {
    "web_search": "web_calls",
    "fetch_url_to_workspace": "web_calls",
}

class QuotaAbortException(BaseException):
    """Raised when a tool is called repeatedly despite being over quota, indicating an LLM loop."""
    pass

def check_quota(tool_name: str) -> str | None:
    """Check if the specific tool has exceeded its per-invocation quota."""
    ctx = tool_quotas_ctx.get()
    tool_name = _QUOTA_ALIASES.get(tool_name, tool_name)
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
                f"STOP CALLING TOOLS NOW. Do NOT call think_tool. Do NOT reflect on "
                f"being blocked. Write your findings so far as your FINAL ANSWER in "
                f"plain text and end your turn, stating clearly that you had to stop "
                f"due to quota limits. Any further tool call is a failure."
            )
        ctx[tool_name]["used"] += 1
    return None


def _check_repeat(tool_name: str, args: tuple, kwargs: dict) -> str | None:
    """Check if this tool is being called identically for the Nth consecutive time.

    Returns an error string if threshold exceeded, None otherwise.
    Never raises — returns None (allow call) on any failure.
    State is stored in the per-task quota context dict to persist across calls.
    """
    try:
        ctx = tool_quotas_ctx.get()
        # No persistent store available — return None (can't track, allow)
        if ctx is None:
            return None

        import json

        def _default_serializer(obj):
            return str(obj)

        sorted_kwargs = sorted(kwargs.items())
        sig_data = (args, sorted_kwargs)
        new_sig = json.dumps(sig_data, sort_keys=True, default=_default_serializer)

        # Read current last call state from quota context
        last_call = ctx.get("_last_call")

        if last_call is None:
            # First call — store and allow
            ctx["_last_call"] = {"sig": new_sig, "count": 1}
            return None

        curr_sig = last_call.get("sig")
        count = last_call.get("count", 0)

        if new_sig == curr_sig:
            # Same args — increment count
            count += 1
            if count > _REPEAT_THRESHOLD:
                # Identical-consecutive call detected. A text error does not stop a
                # model in a degenerate self-regeneration lock (it ignores the result
                # entirely), so we hard-abort instead of returning another ignored
                # string. QuotaAbortException is caught by the salvage-on-abort path,
                # which returns the agent's partial work as its result.
                ctx["_last_call"] = {"sig": new_sig, "count": count}
                raise QuotaAbortException(
                    f"Agent trapped in identical-call loop: '{tool_name}' called with "
                    f"identical arguments {count} times in a row. Force-terminating turn."
                )
            # Below threshold — store updated count in place
            ctx["_last_call"] = {"sig": new_sig, "count": count}
            return None
        else:
            # Different args — reset counter
            ctx["_last_call"] = {"sig": new_sig, "count": 1}
            return None
    except Exception:
        # On any failure, allow the call (return None)
        return None

def _get_tool_rule(tool_name: str, rule_key: str, default_val: int) -> int:
    """Extract custom quota rules (like max_lines) for a specific tool."""
    ctx = tool_quotas_ctx.get()
    tool_name = _QUOTA_ALIASES.get(tool_name, tool_name)
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
            if err := _check_repeat(func.__name__, args, kwargs): return err
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                return f"CRITICAL TOOL EXECUTION ERROR: {func.__name__} failed internally.\n\nException Details:\n{traceback.format_exc()}"
        return async_wrapper
    else:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            if err := check_quota(func.__name__): return err
            if err := _check_repeat(func.__name__, args, kwargs): return err
            try:
                return func(*args, **kwargs)
            except Exception as e:
                return f"CRITICAL TOOL EXECUTION ERROR: {func.__name__} failed internally.\n\nException Details:\n{traceback.format_exc()}"
        return sync_wrapper
