"""
Sweep session logs for Reviewer verdicts and the user prompt that produced each.

Reproduces the sweep described in bugs/reviewer-output-format-non-compliance.md:
walks every session JSON, finds delegate_tasks calls with agent_id == "Reviewer",
pulls the verdict from the matching function_result, classifies it with the same
rule as engine.orchestrator._reviewer_verdict_issue, and reports the originating
user prompt per session so before/after comparisons can re-run like-for-like.

Usage:
    python tools/reviewer_verdict_sweep.py [--since YYYY-MM-DD]

--since filters to sessions modified on/after a date (e.g. the fix date 2026-10-05).
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime

SESSIONS_DIR = os.path.expanduser("~/.deep-research-agent/sessions")

def unwrap(text: str) -> str:
    """Strip the engine's result wrapper: '## Result for <task>' header and
    trailing '---'. The guard classifies the raw final_text BEFORE this wrapper
    is added, so the sweep must undo it to apply the same rule."""
    t = (text or "").strip()
    t = re.sub(r"^##\s*Result for\s.*?\n", "", t)
    t = re.sub(r"\n---+\s*$", "", t)
    return t.strip()


# Same conformance rule as the guard: REVIEW PASSED line, or starts with "1."
# and no line-leading dash/asterisk bullets.
def compliant(text: str) -> bool:
    t = unwrap(text)
    if not t:
        return False
    if t.startswith("REVIEW PASSED"):
        return True
    # regexes identical to the guard's (orchestrator.py:62,82)
    if not re.match(r"^\s*1[\.)\s]", t):
        return False
    return not re.search(r"^\s*[-*]\s", t, re.M)


def shape_of(text: str) -> str:
    t = unwrap(text)
    if not t:
        return "empty"
    if t.startswith("REVIEW PASSED"):
        return "pass-line"
    if re.match(r"^\s*1[\.)\s]", t) and not re.search(r"^\s*[-*]\s", t, re.M):
        return "numbered"
    if re.search(r"^\s*[-*]\s", t, re.M):
        return "bullets"
    return "prose/other"


def first_user_prompt(messages) -> str:
    for m in messages:
        if m.get("role") != "user":
            continue
        for c in m.get("contents", []):
            if c.get("type") == "text":
                t = (c.get("text") or "").strip()
                # skip greeting exchanges and slash commands
                if t and t.lower() not in ("hello", "hi") and not t.startswith("/"):
                    return t
    return ""


def sweep(since=None):
    rows = []
    for path in sorted(glob.glob(os.path.join(SESSIONS_DIR, "*.json"))):
        mtime = datetime.fromtimestamp(os.path.getmtime(path))
        if since and mtime.date() < since:
            continue
        try:
            d = json.load(open(path, encoding="utf-8"))
            messages = d["agent_session"]["state"]["in_memory"]["messages"]
        except (KeyError, json.JSONDecodeError):
            continue
        prompt = first_user_prompt(messages)
        if not prompt:
            continue
        # map call_id -> reviewer flag from delegate_tasks calls
        reviewer_call_ids = set()
        for m in messages:
            for c in m.get("contents", []):
                if c.get("type") == "function_call" and c.get("name") == "delegate_tasks":
                    try:
                        args = json.loads(c.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        continue
                    tasks = args.get("tasks") or args.get("task") or []
                    if isinstance(tasks, str):
                        # delegate-tasks-accepts-string-not-list bug: tasks arrives as a JSON string
                        try:
                            tasks = json.loads(tasks)
                        except json.JSONDecodeError:
                            tasks = []
                    if isinstance(tasks, dict):
                        tasks = [tasks]
                    for t in tasks:
                        if isinstance(t, dict) and t.get("agent_id") == "Reviewer":
                            reviewer_call_ids.add(c.get("call_id"))
        if not reviewer_call_ids:
            continue
        for m in messages:
            for c in m.get("contents", []):
                if c.get("type") == "function_result" and c.get("call_id") in reviewer_call_ids:
                    text = c.get("result") or c.get("text") or ""
                    if not isinstance(text, str):
                        text = json.dumps(text)
                    rows.append({
                        "session": os.path.basename(path)[8:16],
                        "mtime": mtime.strftime("%Y-%m-%d"),
                        "prompt": prompt[:120].replace("\n", " "),
                        "shape": shape_of(text),
                        "compliant": compliant(text),
                    })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date())
    args = ap.parse_args()
    rows = sweep(args.since)
    n_ok = sum(r["compliant"] for r in rows)
    print(f"Reviewer verdicts: {len(rows)}   compliant: {n_ok} "
          f"({100*n_ok/len(rows):.0f}%)" if rows else "no Reviewer verdicts found")
    shapes = {}
    for r in rows:
        shapes[r["shape"]] = shapes.get(r["shape"], 0) + 1
    print("shapes:", shapes)
    print()
    for r in rows:
        mark = "OK " if r["compliant"] else "BAD"
        print(f"{mark} {r['mtime']} {r['session']} [{r['shape']:>11}] {r['prompt']}")


if __name__ == "__main__":
    main()
