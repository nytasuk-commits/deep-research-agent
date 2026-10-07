# tui.py per-run state object — implementation plan (defect 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fold `tui.py`'s four module-level mutable globals into one `SessionLogState` object in a new `engine/session_log.py`, with a single module pointer rebound only at the `/new` and `/resume` boundaries.

**Architecture:** `SessionLogState` owns the event log, the two streaming accumulators, the session id, and the turn-start index. `session_log.py` keeps thin wrapper functions (`log_prompt`, `log_stream_content`, `_write_log`) with identical signatures so `tui.py`'s ~20 call sites don't change; the swap helpers (`new_session`, `load_session`) hold the only `global` statement. `tui.py` reads through accessors (`current_events`, `current_turn_start`, `current_session_id`).

**Tech Stack:** Python 3 (venv at `venv/Scripts/python`), pytest 9.1.1, Textual 8.2.8 (`App.run_test()` Pilot tests, driven via `asyncio.run()` inside sync test functions — pytest-asyncio strict mode is NOT configured in this repo, do not add async test functions).

**Spec:** `docs/superpowers/specs/2026-10-07-tui-per-run-state-design.md` — read it alongside this plan; the plan argues from it.

## Global Constraints

- Work on branch `fix/tui-per-run-state` created from `main` @ acbd39e. Do NOT merge to `main` — the user merges after validation (standing rule).
- Test command: `venv/Scripts/python -m pytest tests/ -q`. Suite baseline: 61 passed at acbd39e.
- Writer function signatures and the persisted event-dict shape are **unchanged** — session JSON files written by old code must load in new code (`from_saved` reads `data.get("ui_events", [])`).
- Writer bodies move **verbatim** from `tui.py:91-208`; this is a move, not a rewrite.
- Do not touch `config.yaml`, fast_test, `session_dir_ctx` (defect 2), `web.py` globals, or the review-done heuristic — all out of scope per spec.
- Never write literal tool-call tag sequences in any file (global instruction).
- Commit messages follow repo style: lowercase subject, colon, one-line detail.

## File Structure

| File | Responsibility |
|---|---|
| Create `src/engine/session_log.py` | `SessionLogState` class, the single `_session_state` pointer, swap helpers (`new_session`, `load_session`), turn helpers (`begin_turn`), readers (`current_events`, `current_turn_start`, `current_session_id`), call-site-compat wrappers (`log_prompt`, `log_stream_content`, `_write_log`) |
| Modify `src/engine/tui.py` | Delete globals (`:26-29`), delete the three writer functions (`:91-208`), import from `session_log`, update 8 read/swap sites, drop `import uuid` |
| Create `tests/test_session_log_state.py` | Unit tests for the class + pointer semantics (no Textual import) |
| Create `tests/test_session_log_wiring.py` | AST guards: tui.py never references the migrated names; session_log.py has exactly one module-level mutable assignment; boundaries call the swap helpers |
| Create `tests/test_tui_session_state_pilot.py` | Pilot tests driving the real `BasicTuiAgent`: `/new` swaps state, `/resume` loads saved log into fresh state |
| Modify `tests/test_review_gate_per_turn.py` | Guard at `:70-71` updates from `_turn_start_idx` to `begin_turn` |
| Modify `bugs/tui-module-state-leaks-across-runs.md` | Status line: defect 3 fixed + validated (Task 3) |

---

### Task 1: `session_log.py` — the state object, tested standalone

**Files:**
- Create: `src/engine/session_log.py`
- Test: `tests/test_session_log_state.py`
- Also: commit the spec + this plan; create the branch

**Interfaces:**
- Consumes: nothing (new module). Imports `config` and `engine.orchestrator.delegation_depth_ctx` — no cycle: `engine.orchestrator` imports only `engine.router`.
- Produces: `SessionLogState(events=None, session_id=None)` with attrs `events: list`, `current_call_by_source: dict`, `current_text_by_source: dict`, `session_id: str`, `turn_start_idx: int`; classmethod `from_saved(data: dict, sid: str)`; methods `log_prompt(prompt)`, `log_stream_content(source, content_type, raw_data_dict, depth=None)`, `write_log()`. Module functions: `new_session() -> SessionLogState`, `load_session(data, sid) -> SessionLogState`, `begin_turn()`, `current_events() -> list`, `current_turn_start() -> int`, `current_session_id() -> str`, `log_prompt(prompt)`, `log_stream_content(source, content_type, raw_data_dict, depth=None)`, `_write_log()`. Module pointer: `_session_state`.

- [ ] **Step 1: Create the branch and commit the design docs**

```bash
git checkout -b fix/tui-per-run-state
git add docs/superpowers/specs/2026-10-07-tui-per-run-state-design.md docs/superpowers/plans/2026-10-07-tui-per-run-state.md
git commit -m "Spec + plan: fold tui.py module globals into a per-session SessionLogState (defect 3)"
```

- [ ] **Step 2: Write the failing unit tests**

Create `tests/test_session_log_state.py`:

```python
"""Unit tests for engine/session_log.py — the per-session state object
extracted from tui.py (bugs/tui-module-state-leaks-across-runs.md defect 3).

No Textual import: the class must be testable on its own. Streaming
accumulation semantics are the pre-existing tui.py behaviour, pinned here
so the verbatim move is provably behaviour-preserving.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

import config
from engine import session_log
from engine.session_log import SessionLogState, new_session, load_session, begin_turn


@pytest.fixture(autouse=True)
def _no_persistence(monkeypatch):
    """Never write real session files from unit tests, regardless of the
    user's config."""
    monkeypatch.setitem(config.cfg["settings"], "enable_session_persistence", False)


def test_text_continuation_merges_into_open_entry():
    st = SessionLogState()
    st.log_stream_content("Agent", "text", {"text": "Hello "})
    st.log_stream_content("Agent", "text", {"text": "world"})
    assert len(st.events) == 1
    assert st.events[0]["data"]["text"] == "Hello world"


def test_nameless_call_delta_appends_to_open_call_arguments():
    st = SessionLogState()
    st.log_stream_content("Agent", "function_call",
                          {"call_id": "c1", "name": "web_search", "arguments": "{"})
    st.log_stream_content("Agent", "function_call",
                          {"call_id": None, "arguments": '"q":"x"}'})
    assert len(st.events) == 1
    assert st.events[0]["data"]["arguments"] == '{"q":"x"}'


def test_function_result_closes_accumulators():
    st = SessionLogState()
    st.log_stream_content("Agent", "text", {"text": "hi"})
    st.log_stream_content("Agent", "function_result", {"call_id": "c1", "result": "ok"})
    st.log_stream_content("Agent", "text", {"text": " again"})
    assert len(st.events) == 3
    assert st.events[2]["data"]["text"] == " again"


def test_log_prompt_clears_accumulators_and_appends():
    st = SessionLogState()
    st.log_stream_content("Agent", "text", {"text": "partial"})
    st.log_prompt("next turn")
    assert st.events[-1]["type"] == "prompt"
    assert st.current_text_by_source == {}
    assert st.current_call_by_source == {}


def test_write_log_skips_when_persistence_off():
    st = SessionLogState()
    st.log_prompt("x")  # log_prompt calls write_log; must not raise or write
    assert st.events[0]["data"]["text"] == "x"


def test_new_session_swaps_pointer_and_leaves_old_object_intact():
    old = session_log._session_state
    old.log_prompt("keep me")
    st = new_session()
    assert session_log._session_state is st
    assert st is not old
    assert st.events == []
    assert st.session_id != old.session_id
    assert old.events[0]["data"]["text"] == "keep me"


def test_load_session_owns_the_saved_list():
    data = {"ui_events": [{"source": "User", "type": "prompt", "data": {"text": "restored"}}]}
    st = load_session(data, "abc")
    assert session_log._session_state is st
    assert st.session_id == "abc"
    assert st.events is data["ui_events"]


def test_begin_turn_snapshots_event_index():
    new_session()
    session_log.log_prompt("t1")
    begin_turn()
    assert session_log._session_state.turn_start_idx == 1
    session_log.log_prompt("t2")
    begin_turn()
    assert session_log._session_state.turn_start_idx == 2


def test_wrappers_delegate_through_the_current_pointer():
    st = new_session()
    session_log.log_prompt("through wrapper")
    session_log.log_stream_content("Agent", "text", {"text": "streamed"})
    session_log._write_log()
    assert st.events[0]["data"]["text"] == "through wrapper"
    assert st.events[1]["data"]["text"] == "streamed"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `venv/Scripts/python -m pytest tests/test_session_log_state.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'engine.session_log'`

- [ ] **Step 4: Write `src/engine/session_log.py`**

The three method bodies below are the verbatim move from `tui.py:91-208` with `_session_events` → `self.events`, `_current_call_by_source` → `self.current_call_by_source`, `_current_text_by_source` → `self.current_text_by_source`, `_write_log()` → `self.write_log()`, and the `global` lines dropped. `write_log`'s orchestrator access stays a lazy import inside the method (matches the original module-level `import engine.orchestrator as orchestrator_module` being resolved at call time).

```python
"""Per-session UI-event log state for the TUI and headless front-ends.

Extracted from engine/tui.py for bugs/tui-module-state-leaks-across-runs.md
defect 3: the four module globals (_session_events, _current_call_by_source,
_current_text_by_source, _current_session_id) become one SessionLogState
object. _session_state is the single module-level pointer, rebound only by
new_session() and load_session() — the /new and /resume boundaries. Writer
bodies moved verbatim from tui.py:91-208; streaming accumulation semantics
are unchanged and pinned by tests/test_session_log_state.py.
"""

from datetime import datetime
import json
import uuid
from pathlib import Path

import config
from engine.orchestrator import delegation_depth_ctx


class SessionLogState:
    def __init__(self, events=None, session_id=None):
        self.events = events if events is not None else []
        self.current_call_by_source = {}
        self.current_text_by_source = {}
        self.session_id = session_id or str(uuid.uuid4())
        self.turn_start_idx = 0

    @classmethod
    def from_saved(cls, data: dict, sid: str):
        return cls(events=data.get("ui_events", []), session_id=sid)

    def write_log(self):
        if not config.cfg["settings"].get("enable_session_persistence", False):
            return

        log_dir = Path.home() / f".{config.APP_NAME}" / "sessions"
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / f"session_{self.session_id}.json"

        payload = {
            "timestamp": datetime.now().isoformat(),
            "ui_events": self.events,
            "agent_session": None,
            "session_id": self.session_id
        }

        import engine.orchestrator as orchestrator_module
        if orchestrator_module._session:
            try:
                payload["agent_session"] = orchestrator_module._session.to_dict()
            except Exception:
                pass

        try:
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception:
            pass

    def log_prompt(self, prompt: str):
        self.events.append({
            "timestamp": datetime.now().isoformat(),
            "source": "User",
            "type": "prompt",
            "data": {"text": prompt}
        })
        self.current_call_by_source.clear()
        self.current_text_by_source.clear()
        self.write_log()

    def log_stream_content(self, source: str, content_type: str, raw_data_dict: dict, depth: int = None):
        if depth is None:
            depth = delegation_depth_ctx.get()

        if content_type == "text" or content_type == "reasoning":
            text_val = raw_data_dict.get("text")
            if not text_val: return
            self.current_call_by_source[source] = None

            idx = self.current_text_by_source.get(source)
            if idx is not None and idx < len(self.events) and self.events[idx]["type"] == content_type:
                self.events[idx]["data"]["text"] += text_val
            else:
                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "source": source,
                    "type": content_type,
                    "data": {"text": text_val},
                    "depth": depth
                }
                self.events.append(entry)
                self.current_text_by_source[source] = len(self.events) - 1

        elif content_type == "function_call":
            self.current_text_by_source[source] = None

            call_id = raw_data_dict.get("call_id")
            name = raw_data_dict.get("name")
            arguments = raw_data_dict.get("arguments", "")

            if call_id:
                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "source": source,
                    "type": "function_call",
                    "data": {
                        "call_id": call_id,
                        "name": name,
                        "arguments": arguments
                    },
                    "depth": depth
                }
                self.events.append(entry)
                self.current_call_by_source[source] = len(self.events) - 1
            else:
                idx = self.current_call_by_source.get(source)
                if idx is not None and idx < len(self.events):
                    if arguments:
                        self.events[idx]["data"]["arguments"] += arguments

        elif content_type == "function_result":
            self.current_text_by_source[source] = None
            self.current_call_by_source[source] = None

            entry = {
                "timestamp": datetime.now().isoformat(),
                "source": source,
                "type": "function_result",
                "data": raw_data_dict,
                "depth": depth
            }
            self.events.append(entry)

        elif content_type in ("subagent_start", "subagent_end"):
            self.current_text_by_source[source] = None
            self.current_call_by_source[source] = None

            entry = {
                "timestamp": datetime.now().isoformat(),
                "source": source,
                "type": content_type,
                "data": raw_data_dict,
                "depth": depth
            }
            self.events.append(entry)

        self.write_log()


_session_state = SessionLogState()


def new_session() -> SessionLogState:
    global _session_state
    _session_state = SessionLogState()
    return _session_state


def load_session(data: dict, sid: str) -> SessionLogState:
    global _session_state
    _session_state = SessionLogState.from_saved(data, sid)
    return _session_state


def begin_turn() -> None:
    _session_state.turn_start_idx = len(_session_state.events)


def current_events() -> list:
    return _session_state.events


def current_turn_start() -> int:
    return _session_state.turn_start_idx


def current_session_id() -> str:
    return _session_state.session_id


def log_prompt(prompt: str):
    _session_state.log_prompt(prompt)


def log_stream_content(source: str, content_type: str, raw_data_dict: dict, depth: int = None):
    _session_state.log_stream_content(source, content_type, raw_data_dict, depth)


def _write_log():
    _session_state.write_log()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/Scripts/python -m pytest tests/test_session_log_state.py -v`
Expected: 9 passed

- [ ] **Step 6: Run the full suite (tui.py untouched so far — must stay green)**

Run: `venv/Scripts/python -m pytest tests/ -q`
Expected: 70 passed (61 baseline + 9 new)

- [ ] **Step 7: Commit**

```bash
git add src/engine/session_log.py tests/test_session_log_state.py
git commit -m "session_log.py: SessionLogState owns the event log, accumulators, id and turn index — bodies moved verbatim from tui.py"
```

---

### Task 2: Switch `tui.py` to the state object

**Files:**
- Modify: `src/engine/tui.py` (delete `:26-29` and `:91-208`; update 8 sites; drop `import uuid` at `:15`)
- Test: `tests/test_session_log_wiring.py` (create), `tests/test_tui_session_state_pilot.py` (create), `tests/test_review_gate_per_turn.py` (modify `:70-71`)

**Interfaces:**
- Consumes: Task 1's `session_log` module — `log_prompt`, `log_stream_content`, `_write_log`, `new_session`, `load_session`, `begin_turn`, `current_events`, `current_turn_start`, `current_session_id`.
- Produces: `tui.py` with zero references to the four migrated names and zero `global` statements for them; `BasicTuiAgent` behaviour unchanged at the UI level.

- [ ] **Step 1: Write the failing AST guards**

Create `tests/test_session_log_wiring.py`:

```python
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
```

- [ ] **Step 2: Write the failing Pilot tests**

Create `tests/test_tui_session_state_pilot.py`:

```python
"""Pilot tests: drive the real BasicTuiAgent headlessly to prove session
state isolation across /new and /resume in one process — the live-equivalent
validation for bugs/tui-module-state-leaks-across-runs.md defect 3
(user-approved 2026-10-07).

Async drivers run inside asyncio.run() from sync test functions:
pytest-asyncio strict mode is not configured in this repo.
"""

import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

import config
from engine import session_log
import engine.orchestrator as orchestrator_module
from engine.sdk import AgentBuilder
from engine.tui import BasicTuiAgent


@pytest.fixture(autouse=True)
def _no_persistence(monkeypatch):
    monkeypatch.setitem(config.cfg["settings"], "enable_session_persistence", False)


def _builder():
    return AgentBuilder(name="test", description="d", instructions="i", tools=[])


class _NoAgentTui(BasicTuiAgent):
    """Auto-prime (on_mount schedules run_agent("Hello") at +0.1s) and real
    agent turns are out of scope for state-isolation tests. The override is
    sync to match the @work calling convention."""

    def run_agent(self, query, show_user_message=True):
        return None


def test_new_command_swaps_the_state_object():
    async def drive():
        app = _NoAgentTui(_builder())
        async with app.run_test() as pilot:
            session_log.log_stream_content("Agent", "text", {"text": "run one"})
            old = session_log._session_state
            assert old.events

            await pilot.click("#prompt-input")
            await pilot.type("#prompt-input", "/new")
            await pilot.press("enter")
            await pilot.pause()

            new = session_log._session_state
            assert new is not old
            assert new.events == []
            assert new.session_id != old.session_id
            # the old run's log is unreachable from the live pointer and
            # was not mutated by the swap
            assert old.events[0]["data"]["text"] == "run one"

    asyncio.run(drive())


def test_resume_loads_saved_log_into_fresh_state():
    sid = "test-" + uuid.uuid4().hex[:8]
    log_dir = Path.home() / f".{config.APP_NAME}" / "sessions"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"session_{sid}.json"
    saved = {
        "timestamp": "2026-10-07T00:00:00",
        "ui_events": [{"timestamp": "t", "source": "User", "type": "prompt",
                       "data": {"text": "restored"}}],
        "agent_session": None,
        "session_id": sid,
    }
    log_file.write_text(json.dumps(saved), encoding="utf-8")

    async def fake_create_local_agent(builder=None, subagent_callback=None,
                                      session_data=None, notify=None):
        return None, None

    async def drive():
        app = _NoAgentTui(_builder())
        async with app.run_test() as pilot:
            session_log.log_stream_content("Agent", "text", {"text": "current run"})
            old = session_log._session_state
            await app._load_session_by_id(sid)
            await pilot.pause()
            st = session_log._session_state
            assert st is not old
            assert st.session_id == sid
            assert [e["data"]["text"] for e in st.events] == ["restored"]

    orig = orchestrator_module.create_local_agent
    orchestrator_module.create_local_agent = fake_create_local_agent
    try:
        asyncio.run(drive())
    finally:
        orchestrator_module.create_local_agent = orig
        log_file.unlink(missing_ok=True)
```

- [ ] **Step 3: Update the existing turn-start guard's name**

In `tests/test_review_gate_per_turn.py`, replace lines 70-71:

```python
    assert "_turn_start_idx" in dumped, "run_agent wrapper does not record the turn-start index"
    assert "_turn_review_done" in dumped or "_turn_start_idx" in dumped
```

with:

```python
    assert "begin_turn" in dumped, "run_agent wrapper does not record the turn-start index"
```

- [ ] **Step 4: Run the new tests to verify they fail**

Run: `venv/Scripts/python -m pytest tests/test_session_log_wiring.py tests/test_tui_session_state_pilot.py tests/test_review_gate_per_turn.py -v`
Expected: wiring guards FAIL (tui.py still references migrated names, boundaries don't call helpers); Pilot `test_new_command_swaps_the_state_object` FAILS (`/new` mutates the old object instead of swapping); `test_resume_loads_saved_log_into_fresh_state` FAILS (`st is old`); the updated review-gate guard FAILS (`begin_turn` not yet in `run_agent`).

- [ ] **Step 5: Edit `tui.py` — delete the old state**

Delete lines 26-29 (the four globals). Delete the three functions `_write_log`, `log_prompt`, `log_stream_content` (`:91-208` in the pre-edit file). Delete `import uuid` (`:15`) — after the edits nothing in `tui.py` uses it. Add after the existing engine imports (`:7-8`):

```python
from engine.session_log import (
    log_prompt, log_stream_content, _write_log,
    new_session, load_session, begin_turn,
    current_events, current_turn_start, current_session_id,
)
```

- [ ] **Step 6: Edit `tui.py` — the eight sites**

6a. Banner (`:517`): inside the `status_line` f-string, replace `{_current_session_id}` with `{current_session_id()}`.

6b. `/new` handler (`:620-624`): replace

```python
            global _current_session_id, _session_events, _current_call_by_source, _current_text_by_source
            _current_session_id = str(uuid.uuid4())
            _session_events.clear()
            _current_call_by_source.clear()
            _current_text_by_source.clear()
```

with

```python
            new_session()
```

6c. `/toggle_persistence` (`:645`): replace `log_file = log_dir / f"session_{_current_session_id}.json"` with `log_file = log_dir / f"session_{current_session_id()}.json"`.

6d. `_load_session_by_id` (`:709-719`): replace

```python
            global _session_events, _current_session_id, _current_call_by_source, _current_text_by_source
            ui_events = data.get("ui_events", [])
            state_dict = data.get("agent_session", None)
            
            self._is_agent_running = False
            self.workers.cancel_all()
            
            _session_events = ui_events
            _current_session_id = sid
            _current_call_by_source.clear()
            _current_text_by_source.clear()
```

with

```python
            ui_events = data.get("ui_events", [])
            state_dict = data.get("agent_session", None)

            self._is_agent_running = False
            self.workers.cancel_all()

            load_session(data, sid)
```

(`load_session` takes ownership of the same `ui_events` list object, so `reconstruct_ui_from_events(ui_events)` below is unaffected.)

6e. `run_agent` wrapper (`:959`): replace

```python
        self._turn_start_idx = len(_session_events)
```

with

```python
        begin_turn()
```

The comment above it ("Snapshot where this turn starts in the accumulated event list so the review gate can scope its scan to this turn only.") stays as-is — it names no old identifier.

6f. Review gate (`:1199`): replace

```python
                review_done = _turn_review_done(_session_events, getattr(self, "_turn_start_idx", 0))
```

with

```python
                review_done = _turn_review_done(current_events(), current_turn_start())
```

6g. Headless `--resume` (`:1400-1404`): replace

```python
            global _session_events, _current_session_id, _current_call_by_source, _current_text_by_source
            _session_events = data.get("ui_events", [])
            _current_session_id = session_id
            _current_call_by_source.clear()
            _current_text_by_source.clear()
```

with

```python
            load_session(data, session_id)
```

6h. Headless banner (`:1452`): replace `sid = "N/A (Memory disabled)" if not session else _current_session_id` with `sid = "N/A (Memory disabled)" if not session else current_session_id()`.

- [ ] **Step 7: Run the new tests to verify they pass**

Run: `venv/Scripts/python -m pytest tests/test_session_log_wiring.py tests/test_tui_session_state_pilot.py tests/test_review_gate_per_turn.py -v`
Expected: all PASS. If a Pilot test hangs, check the `_NoAgentTui.run_agent` override is sync (a coroutine-returning override under `set_timer` produces an un-awaited coroutine, not a hang — a hang means the Textual pilot didn't settle; add `await pilot.pause()` after each action).

- [ ] **Step 8: Run the full suite**

Run: `venv/Scripts/python -m pytest tests/ -q`
Expected: 75 passed (61 baseline + 9 state + 3 wiring + 2 pilot). The review-gate guard edit removes one assert, not a test, so that file's count is unchanged.

- [ ] **Step 9: Commit**

```bash
git add src/engine/tui.py tests/test_session_log_wiring.py tests/test_tui_session_state_pilot.py tests/test_review_gate_per_turn.py
git commit -m "tui.py drops its module globals: one SessionLogState pointer, swapped only at /new and /resume; Pilot tests prove per-run isolation"
```

---

### Task 3: Headless smoke + tracking-doc status

**Files:**
- Modify: `bugs/tui-module-state-leaks-across-runs.md` (status line)

**Interfaces:**
- Consumes: the refactored `tui.py` end-to-end (headless path exercises `log_prompt`/`log_stream_content`/`_write_log`/`begin_turn`-adjacent gate code and persistence).
- Produces: validated branch ready for the user's merge decision.

- [ ] **Step 1: Headless smoke run (requires the model endpoint up)**

Run: `venv/Scripts/python src/app.py --prompt "What is 2+2? Answer in one sentence." --auto-approve`
Expected: banner prints a Session ID, the agent answers, "Task completed in N seconds." appears, no traceback. If the endpoint is down, STOP and report — do not mark the bug fixed.

- [ ] **Step 2: Verify the persistence log**

Find the newest `session_*.json` under `~/.deep-research-agent/sessions/` (mtime after the smoke). Verify: `session_id` matches the banner's, `ui_events` is non-empty and contains the prompt event plus at least one `text` event, and the JSON loads.

- [ ] **Step 3: Update the bug status line**

In `bugs/tui-module-state-leaks-across-runs.md`, change the Status line to record: defect 3 FIXED 2026-10-07 on `fix/tui-per-run-state` — globals folded into `engine/session_log.py::SessionLogState`, single pointer swapped at `/new`/`/resume`; pinned by `tests/test_session_log_state.py` (9), `tests/test_session_log_wiring.py` (3 AST guards), `tests/test_tui_session_state_pilot.py` (2 Pilot tests, the live-equivalent validation approved 2026-10-07); headless smoke confirmed persistence end-to-end. Defect 2 remains the open design question.

- [ ] **Step 4: Full suite one final time**

Run: `venv/Scripts/python -m pytest tests/ -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add bugs/tui-module-state-leaks-across-runs.md
git commit -m "Defect 3 closed: tui.py state now owned by SessionLogState; Pilot + wiring + smoke evidence recorded"
```

- [ ] **Step 6: Report to the user — do NOT merge**

Summarize: suite count, Pilot results, smoke result, branch tip. The user merges `fix/tui-per-run-state` to `main` (standing rule).

---

## Self-review record

- Spec coverage: new module (Task 1), tui.py table rows 1-8 (Task 2 steps 5-6, all eight), edge cases (behaviour-preserving; Pilot tests pin the swap semantics), testing items 1-4 (Tasks 1-3), out-of-scope items (Global Constraints). No gaps.
- Placeholders: none — every code step carries full code.
- Type consistency: `new_session`/`load_session`/`begin_turn`/`current_events`/`current_turn_start`/`current_session_id` names identical across Tasks 1-2 and the guards; `SessionLogState.from_saved(data, sid)` identical in class and `load_session`.
