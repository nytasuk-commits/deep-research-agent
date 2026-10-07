# tui.py per-run state object — design (defect 3)

**Date:** 2026-10-07
**Bug:** `bugs/tui-module-state-leaks-across-runs.md` defect 3 (Low, structural)
**Branch point:** main @ acbd39e. Line numbers below are as of that commit.

## Problem

`src/engine/tui.py:26-29` holds four module-level mutable globals — `_session_events`,
`_current_call_by_source`, `_current_text_by_source`, `_current_session_id` — written by
three free-floating module functions (`_write_log:91`, `log_prompt:119`,
`log_stream_content:131`) that both the TUI path (~12 call sites) and the headless path
(`run_cli`, `cli_subagent_callback`, ~8 call sites) call, and rebound with `global`
statements at three session boundaries (`/new:620`, TUI `_load_session_by_id:709`,
headless `--resume:1400`). `/new` does clear them, so the original "run N+1 inherits run
N" claim is partially stale — the defect is the absence of ownership discipline:
process-global mutable state with scattered writers and no single swap point.

The globals are private to `tui.py`: no module imports them; only test docstrings and AST
source-guards (`tests/test_review_gate_per_turn.py`) reference the names.

## Decisions (user-approved 2026-10-07)

1. **API shape:** state class + one module-level current pointer. Writer function
   signatures stay identical; call sites unchanged.
2. **Lifetime:** per-session. One `SessionLogState` object per session, swapped at
   `/new`/`/resume`. (Not per-turn: events accumulate across turns because persistence
   writes the whole log, and the review gate's turn scan indexes *within* the session log.
   Not a contextvar: wrong lifetime, and Textual workers run in a different async context
   — the codebase already hit contextvar teardown there, `tui.py:545-546`.)
3. **Module layout:** extract to a new `src/engine/session_log.py`; `tui.py` imports the
   three wrapper names back. Shrinks the 1678-line module; class unit-testable without
   Textual.
4. **Validation:** Textual Pilot tests (drive the real app headlessly) + AST guards +
   unit tests; plus one headless smoke run for the persistence path.

## Design

### New module `src/engine/session_log.py`

```python
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

    def log_prompt(self, prompt): ...          # body moved from tui.py:119-129
    def log_stream_content(self, source, content_type, raw_data_dict, depth=None): ...
                                               # body moved from tui.py:131-208 verbatim
    def write_log(self): ...                   # body moved from tui.py:91-117

_session_state = SessionLogState()             # the ONLY module-level mutable global

def new_session() -> SessionLogState:          # global _session_state; rebind to fresh
def load_session(data, sid) -> SessionLogState:  # global rebind to from_saved(data, sid)
def begin_turn() -> None:                      # _session_state.turn_start_idx = len(events)
def current_events() -> list
def current_turn_start() -> int
def current_session_id() -> str

# thin wrappers, kept so tui.py call sites do not change:
def log_prompt(prompt): _session_state.log_prompt(prompt)
def log_stream_content(source, content_type, raw_data_dict, depth=None): ...
def _write_log(): _session_state.write_log()
```

Bodies move **verbatim** — the streaming accumulation semantics (open-text merge,
nameless-call-delta argument append, accumulator close on `function_result`) are pinned by
existing behaviour and get new unit tests, not rewrites. `write_log` keeps its
try/except around `orchestrator_module._session.to_dict()` with a lazy import inside the
method. No import cycle: `engine.orchestrator` imports only `engine.router`.

### `tui.py` changes

Every `global` statement for the migrated names disappears (AST-guarded).

| Site | Today | After |
|---|---|---|
| `/new` (`:620-624`) | `global` + re-id + 3x `.clear()` | `new_session()` |
| TUI `/resume` (`:709-719`) | `global` + rebind 2 + clear 2 | `load_session(data, sid)` |
| headless `--resume` (`:1400-1404`) | same shape | `load_session(data, sid)` |
| `run_agent` wrapper (`:959`) | `self._turn_start_idx = len(_session_events)` | `begin_turn()` |
| review gate (`:1199`) | `_turn_review_done(_session_events, self._turn_start_idx)` | `_turn_review_done(current_events(), current_turn_start())` |
| banners (`:517`, `:1452`), `/toggle_persistence` (`:645`) | read `_current_session_id` | `current_session_id()` |
| ~20 writer calls | module functions | same names imported from `engine.session_log` |

`_turn_review_done` (`tui.py:31-44`) stays a pure helper in `tui.py` — its existing tests
import it directly.

### Edge cases (behaviour-preserving)

- **Swap while a worker is mid-stream** (`/new`/`/resume` during a run): today a late
  `log_stream_content` appends to the cleared/rebound global list; after the refactor it
  appends to the new state object. Equivalent hazard, not worse. Worker cancellation is
  out of scope.
- **Persistence OFF:** `write_log` early-return unchanged.
- **`from_saved` takes ownership** of the decoded `ui_events` list (same as today's
  `_session_events = ui_events`); `reconstruct_ui_from_events(ui_events)` keeps working
  off the same list object.
- **`turn_start_idx` moves** from the App (`self._turn_start_idx`) to the state object,
  where it indexes `events`. A swapped state resets it naturally.

## Testing

1. **`tests/test_session_log_state.py`** (no Textual import): streaming accumulation
   semantics (text continuation merges into the open entry; nameless call deltas append
   to the open call's arguments; `function_call`/`function_result`/`subagent_*` close the
   opposite accumulator); `new_session()` changes id and empties events; `from_saved`
   owns the loaded list; `begin_turn` snapshots the index.
2. **`tests/test_tui_session_state_pilot.py`** (live-equivalent for the TUI path):
   `BasicTuiAgent.run_test()` — seed events via `log_stream_content`, `/new`, assert fresh
   id + empty events + old events unreachable; `/resume <id>`, assert the state object
   owns the loaded log; two runs in one process share no events.
3. **AST guards:** `session_log.py` has exactly one module-level mutable assignment
   (`_session_state`); `tui.py` has zero `global` statements for the migrated names;
   `/new` and `_load_session_by_id` call `new_session()`/`load_session()`; `run_agent`
   still snapshots the turn start — the existing guard at
   `tests/test_review_gate_per_turn.py:70` updates from `_turn_start_idx` to the new
   name, intent unchanged.
4. Full suite green (61 at acbd39e), plus one headless smoke
   (`venv\Scripts\python src/app.py --prompt ... --auto-approve`) confirming the
   persistence log still writes end-to-end.

Commit gate: standing rule — unit green is not enough; the Pilot tests are the live
validation for this path (user-approved 2026-10-07), plus the headless smoke.

## Out of scope

- **Defect 2** (`session_dir_ctx` set per turn at `tui.py:975`/`:1338`): untouched. The
  state object is the natural home for the run-folder name once the per-session-vs-per-turn
  decision is made; `SessionLogState` is the hook, not this change.
- `web.py` module globals — `backlog/search-module-level-state.md`.
- Review-done heuristic — `backlog/review-done-detection-fragile-heuristic.md`.
- Worker cancellation on `/new`/`/resume` — unchanged behaviour.
