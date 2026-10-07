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
import time
import uuid
from pathlib import Path

import config
from engine.orchestrator import delegation_depth_ctx


def _mint_run_dir() -> str:
    return f"run_{int(time.time())}"


class SessionLogState:
    def __init__(self, events=None, session_id=None):
        self.events = events if events is not None else []
        self.current_call_by_source = {}
        self.current_text_by_source = {}
        self.session_id = session_id or str(uuid.uuid4())
        self.turn_start_idx = 0
        # One workspace run folder per session (defect 2): minted at state
        # creation, carried in the session file so /resume re-enters the same
        # folder. from_saved overwrites with the stored value — None means a
        # pre-fix file, and ensure_run_dir() mints lazily for it.
        self.run_dir = _mint_run_dir()

    @classmethod
    def from_saved(cls, data: dict, sid: str):
        st = cls(events=data.get("ui_events", []), session_id=sid)
        st.run_dir = data.get("run_dir")
        return st

    def ensure_run_dir(self) -> str:
        if self.run_dir is None:
            self.run_dir = _mint_run_dir()
        return self.run_dir

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
            "session_id": self.session_id,
            "run_dir": self.run_dir
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


def ensure_run_dir() -> str:
    return _session_state.ensure_run_dir()


def current_run_dir():
    return _session_state.run_dir


def log_prompt(prompt: str):
    _session_state.log_prompt(prompt)


def log_stream_content(source: str, content_type: str, raw_data_dict: dict, depth: int = None):
    _session_state.log_stream_content(source, content_type, raw_data_dict, depth)


def _write_log():
    _session_state.write_log()
