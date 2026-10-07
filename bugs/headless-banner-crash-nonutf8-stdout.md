# Headless mode crashes at the config banner when stdout is not a UTF-8 console

**Status:** FIXED 2026-10-07 and live-validated — `_ensure_utf8_streams()` at the top of `cli_main` reconfigures stdout/stderr to UTF-8 with `errors="replace"`. The exact crashing launch (redirected capture, no `PYTHONIOENCODING`) now prints the banner with the warning emoji and starts the task.
**Severity:** Medium — any redirection of headless output (pipe, `> file`, CI, background task capture) kills the run before the task starts; interactive console runs are unaffected
**Found:** 2026-10-07, live crash while launching a background validation run

## Symptom

`python src/app.py --prompt ... --auto-approve` with stdout redirected to a file dies instantly:

```
File "src/engine/tui.py", line 1426, in run_cli
    sys.stdout.write(
        f"\n\033[1;32m{config.APP_TITLE} (Headless Mode)\033[0m\n"
        ...
UnicodeEncodeError: 'charmap' codec can't encode characters in position 539-540: character maps to <undefined>
```

Position 539-540 is the `⚠️` in the AUTO-APPROVE warning line. The router priming lines print fine (ASCII + box chars that cp1252 happens to cover); the banner's emoji is the first unencodable character.

## Root cause

On Windows, when stdout is not an interactive console, Python falls back to the locale encoding (cp1252) instead of UTF-8. `run_cli` writes the config banner — which contains `⚠️` (and the auto-approve warning) — with plain `sys.stdout.write`, so the first emoji raises `UnicodeEncodeError` and the process exits 1 before the agent runs. Later writes are also exposed: agent text streamed via `sys.stdout.write(content.text)` and search-result emoji (`🔍`) would hit the same wall even if the banner were fixed.

## Evidence

Live traceback above (background task capture file, 2026-10-07). Workaround confirmed to unblock: launch with `PYTHONIOENCODING=utf-8`.

## Fix applied (2026-10-07)

`_ensure_utf8_streams()` (tui.py, called first thing in `cli_main` so both TUI and headless paths are covered) reconfigures both streams to `encoding="utf-8", errors="replace"`, each in a try/except so an exotic stream object can't break startup. `errors="replace"` keeps one unencodable character from killing a 15-minute run.

Pinned by `tests/test_utf8_streams.py` (3 cases, watched RED first): the banner emoji writes as UTF-8 bytes through a cp1252-simulated stream, a lone surrogate degrades instead of raising, and an AST guard that `cli_main` calls the guard. Suite: 61 passed.

**Live validation:** the exact failing launch shape — `venv/Scripts/python src/app.py --prompt ... --auto-approve` with stdout captured to a file, no `PYTHONIOENCODING` — now prints `Deep Research Agent (Headless Mode)` and the `⚠️ AUTO-APPROVE OVERRIDE` line and starts the task (smoke run 2026-10-07, stopped after the banner).

## Related

- `backlog/session-persistence-quadratic-io.md` — adjacent headless/session-log mechanics.
