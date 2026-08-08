from typing import Dict, List
import os
import re
import contextvars
from agent_framework import tool
from tools.core import with_quota, _get_tool_rule, tool_quotas_ctx

# --- WORKSPACE FILE SYSTEM ---
_IN_MEMORY_FS: Dict[str, str] = {}
session_dir_ctx = contextvars.ContextVar('session_dir', default="")

def _get_workspace_type() -> str:
    from config import cfg
    return cfg.get("settings", {}).get("workspace", {}).get("type", "memory")

def _get_workspace_dir() -> str:
    from config import cfg
    return cfg.get("settings", {}).get("workspace", {}).get("dir", ".")

def _get_safe_path(filename: str) -> str:
    # Safely allow subdirectories while blocking traversal hacks
    if ".." in filename or filename.startswith("/") or filename.startswith("\\"):
        return ""
    
    session_dir = session_dir_ctx.get()
    if session_dir:
        filename = os.path.join(session_dir, filename)

    if _get_workspace_type() == "disk":
        return os.path.join(_get_workspace_dir(), filename)
    return filename

def get_workspace_files() -> List[str]:
    """Helper for TUI to list files agnostic of storage backend.
    
    Returns bare filenames (without session prefix) so agents can pass them
    directly to read_workspace_file/grep_workspace_file. The session prefix
    is transparently added by _get_safe_path inside those functions.
    """
    session_dir = session_dir_ctx.get()
    
    if _get_workspace_type() == "disk":
        d = _get_workspace_dir()
        if session_dir:
            d = os.path.join(d, session_dir)
        if not os.path.isdir(d): return []
        res = []
        for root, _, files in os.walk(d):
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), d)
                res.append(rel.replace("\\", "/"))
        return res
        
    if session_dir:
        prefix = session_dir + "/"
        return [k[len(prefix):] for k in _IN_MEMORY_FS.keys() if k.startswith(prefix)]
    return list(_IN_MEMORY_FS.keys())

def get_workspace_file_content(filename: str) -> str | None:
    """Helper for TUI to read a file agnostic of storage backend."""
    path = _get_safe_path(filename)
    if not path: return None
    if _get_workspace_type() == "disk":
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                return None
        return None
    return _IN_MEMORY_FS.get(path)

@tool
@with_quota
def read_workspace_file(filename: str, start_line: int = 1, end_line: int = -1) -> str:
    """Read a stored text file. Use start_line and end_line bounds to read large files safely. Both bounds are 1-indexed."""
    try:
        content = get_workspace_file_content(filename)
        if content is None: return f"Error: '{filename}' not found."

        lines = content.splitlines()
        total = len(lines)

        max_lines = _get_tool_rule("read_workspace_file", "max_lines", 300)

        # Capture whether this is an unbounded request BEFORE end_line is reassigned
        # Unbounded means: caller did not narrow the range (start_line <= 1 and original end_line == -1)
        unbounded = (start_line <= 1 and end_line == -1)

        if end_line == -1: end_line = total

        start = max(1, start_line)
        end = min(total, end_line)

        if (end - start + 1) > max_lines:
            # First oversized read of a file: serve the first max_lines as a useful
            # slice rather than wasting the charged call. The agent gets content AND
            # the file length, then uses grep for the rest.
            #
            # REPEAT oversized read of the SAME file: refuse ONLY for unbounded reads.
            # Serving the same slice again lets an agent loop on an identical unbounded
            # read (observed: 40 identical calls on one file in session_6b67a03d).
            # Refusing forces the correct grep-then-targeted-read pattern.
            #
            # Bounded reads that exceed max_lines (e.g., lines 401-836 with max=400) are
            # allowed: we serve max_lines from start_line and tell agent to continue.
            _ctx = tool_quotas_ctx.get()
            _sliced = None
            if isinstance(_ctx, dict):
                _sliced = _ctx.setdefault("_sliced_files", set())
            if _sliced is not None and filename in _sliced and unbounded:
                return (f"Error: You have already been served the first {max_lines} lines of "
                        f"'{filename}' ({total} lines total). Requesting it again returns nothing new. "
                        f"You MUST now either call grep_workspace_file on this file to locate the "
                        f"content you need, or call read_workspace_file with explicit start_line and "
                        f"end_line bounds spanning no more than {max_lines} lines.")
            if _sliced is not None and unbounded:
                _sliced.add(filename)
            # For bounded reads exceeding max_lines, serve max_lines from start_line
            # without adding to _sliced_files
            end = min(total, start + max_lines - 1)
            chunk = "\n".join(lines[start - 1:end])
            if unbounded:
                return (f"--- {filename} [Lines {start}-{end} of {total}] ---\n{chunk}\n\n"
                        f"[NOTE: This file is {total} lines; you have been given lines {start}-{end}. "
                        f"Do NOT request this file again without bounds — it will be refused. Use "
                        f"grep_workspace_file on this file to locate content beyond line {end}, then "
                        f"read only those line ranges.]")
            else:
                return (f"--- {filename} [Lines {start}-{end} of {total}] ---\n{chunk}\n\n"
                        f"[NOTE: This file is {total} lines; you have been given lines {start}-{end}. "
                        f"Request lines {end + 1} onward for the rest.]")
            
        chunk = "\n".join(lines[start - 1:end])
        return f"--- {filename} [Lines {start}-{end} of {total}] ---\n{chunk}"
    except Exception as e:
        import traceback
        return f"Error: {e}\n\nTraceback:\n{traceback.format_exc()}"

@tool
@with_quota
def write_workspace_file(filename: str, content: str) -> str:
    """Save content to your workspace."""
    try:
        path = _get_safe_path(filename)
        if not path: return f"Error: Invalid filename '{filename}'."
        if _get_workspace_type() == "disk":
            parent_dir = os.path.dirname(path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Wrote '{filename}' to disk."
        else:
            _IN_MEMORY_FS[path] = content
            return f"Wrote '{filename}' to memory."
    except Exception as e:
        import traceback
        return f"Error: {e}\n\nTraceback:\n{traceback.format_exc()}"

@tool
@with_quota
def list_workspace_files() -> str:
    """List all files in your workspace, showing line and character counts."""
    files = get_workspace_files()
    if not files: return "Workspace empty."
    res = []
    for k in sorted(files):
        content = get_workspace_file_content(k) or ""
        res.append(f"{k} (Lines: {len(content.splitlines())}, Chars: {len(content)})")
    return "\n".join(res)

@tool
@with_quota
def grep_workspace_file(filename: str, pattern: str, context_lines: int = 2) -> str:
    """Search for a regex pattern within a file, returning matching lines with surrounding context."""
    try:
        content = get_workspace_file_content(filename)
        if content is None: return f"Error: '{filename}' not found."
        
        lines = content.splitlines()
        max_matches = _get_tool_rule("grep_workspace_file", "max_matches", 10)
        
        compiled = re.compile(pattern, re.IGNORECASE)
        matches = []
        for i, line in enumerate(lines):
            if compiled.search(line):
                matches.append(i)
                if len(matches) >= max_matches:
                    break
                    
        if not matches: return f"No matches found for '{pattern}'."
        
        out = []
        for match_idx in matches:
            start = max(0, match_idx - context_lines)
            end = min(len(lines), match_idx + context_lines + 1)
            out.append(f"--- Match near line {match_idx + 1} ---")
            for j in range(start, end):
                prefix = "> " if j == match_idx else "  "
                out.append(f"{j + 1:04d}{prefix}{lines[j]}")
                
        return "\n".join(out)
    except Exception as e:
        import traceback
        return f"Grep Error: {e}\n\nTraceback:\n{traceback.format_exc()}"

@tool
@with_quota
def remove_workspace_file(filename: str) -> str:
    """A destructive action that mandates human oversight. Deletes a file."""
    try:
        path = _get_safe_path(filename)
        if not path: return f"Error: Invalid filename '{filename}'."
        if _get_workspace_type() == "disk":
            if os.path.exists(path):
                os.remove(path)
                return f"Deleted: {filename}"
        else:
            if path in _IN_MEMORY_FS:
                del _IN_MEMORY_FS[path]
                return f"Deleted: {filename}"
        return f"Error: '{filename}' not found."
    except Exception as e:
        import traceback
        return f"Error: {e}\n\nTraceback:\n{traceback.format_exc()}"
