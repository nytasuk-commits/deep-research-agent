import os
from agent_framework import tool
from tools.core import with_quota
from tools.fs import _get_workspace_type, _get_workspace_dir, get_workspace_file_content, _IN_MEMORY_FS

@tool
@with_quota
def write_todos(todos: str, named_entities: list[str] | None = None) -> str:
    """Write or update a todo list for the orchestrator task.

    Use this to track your plan and mark items as completed.
    Use markdown checkboxes so you can see progress at a glance:

        - [x] Completed task
        - [ ] Pending task
        - [ ] Another pending task

    Call read_todos() first to see the current list, then rewrite the
    full list with updated checkboxes when items are done.

    Args:
        todos: The full todo list string with checkboxes to save.
        named_entities: If the query explicitly names specific entities to
            research or compare (e.g. a list of models, products, or options),
            pass the exact list of those entity names here. Each named entity
            MUST have its OWN separate todo line; you must NOT combine two or
            more named entities into a single todo. This list is validated:
            if any named entities are missing a dedicated todo, or two or more
            are combined onto one line, the write is REJECTED and you must redo
            the list with one todo per named entity.
    """
    # --- Named-entity collapse guard ---
    # The orchestrator has repeatedly collapsed multiple named entities into
    # dimensional todos (e.g. "memory requirements for each model: A, B, C..."),
    # which defeats per-entity budget allocation and silently drops entities.
    # If named_entities are declared, enforce one dedicated todo line per entity
    # and reject any line that combines two or more of them.
    if named_entities:
        entities = [e.strip() for e in named_entities if e and e.strip()]
        if entities:
            todo_lines = [ln for ln in todos.splitlines()
                          if ln.strip().startswith("- [")]
            lower_lines = [ln.lower() for ln in todo_lines]

            # 1. Every named entity must appear in at least one todo line.
            missing = [e for e in entities
                       if not any(e.lower() in ln for ln in lower_lines)]
            if missing:
                return ("Error: TODO list REJECTED — not written. The following "
                        "mandatory named entities have NO todo of their own: "
                        + ", ".join(missing) + ". You MUST create ONE separate "
                        "todo per named entity. Redo write_todos with a dedicated "
                        "'- [ ]' line for each named entity, then continue.")

            # 2. No single todo line may contain two or more named entities
            #    (that is the collapse we are preventing).
            collapsed = []
            for ln, low in zip(todo_lines, lower_lines):
                hits = [e for e in entities if e.lower() in low]
                if len(hits) >= 2:
                    collapsed.append(ln.strip())
            if collapsed:
                return ("Error: TODO list REJECTED — not written. These todo "
                        "lines combine MULTIPLE named entities into one todo, "
                        "which is forbidden: " + " || ".join(collapsed) + ". "
                        "Each named entity is a MANDATORY separate deliverable. "
                        "Redo write_todos with ONE todo per named entity — do "
                        "NOT bundle entities together under a shared dimensional "
                        "todo (e.g. 'memory for each model: A, B, C').")

    try:
        from tools.fs import _get_safe_path
        path = _get_safe_path("_todos.md")
        if not path:
            return "Error: could not resolve path for _todos.md"
        if _get_workspace_type() == "disk":
            parent_dir = os.path.dirname(path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(todos)
        else:
            _IN_MEMORY_FS[path] = todos
        # Clear the read-repeat guard: the list has changed, so the next
        # read_todos should be served rather than refused.
        try:
            from tools.core import tool_quotas_ctx
            _ctx = tool_quotas_ctx.get()
            if isinstance(_ctx, dict):
                _ctx.pop("_last_todos_read", None)
        except Exception:
            pass
        return "Todos saved successfully."
    except Exception as e:
        import traceback
        return f"Error: {e}\n\nTraceback:\n{traceback.format_exc()}"

@tool
@with_quota
def read_todos() -> str:
    """Read the current todo list to review progress.

    Use this before continuing work to see which tasks are done ([x])
    and which are still pending ([ ]).
    """
    try:
        content = get_workspace_file_content("_todos.md")
        if not content:
            return "No todos have been saved yet."
        # Refuse a repeat read that would return the exact same list as the
        # previous read, with no write_todos in between. Re-reading an unchanged
        # list yields nothing new and is a common orchestrator stall (observed:
        # 28 consecutive identical read_todos calls in session_5f93c431). The
        # list only changes when write_todos is called, so an unchanged repeat
        # means the agent must ACT on a todo, not read it again.
        from tools.core import tool_quotas_ctx
        _ctx = tool_quotas_ctx.get()
        if isinstance(_ctx, dict):
            _last = _ctx.get("_last_todos_read")
            if _last is not None and _last == content:
                return ("Error: The todo list has NOT changed since you last read it "
                        "and no write_todos was called in between. Re-reading it gives "
                        "you nothing new. You MUST now EXECUTE the next unchecked todo — "
                        "delegate a task, or write the final report — rather than reading "
                        "the list again.")
            _ctx["_last_todos_read"] = content
        return content
    except Exception as e:
        import traceback
        return f"Error: {e}\n\nTraceback:\n{traceback.format_exc()}"
