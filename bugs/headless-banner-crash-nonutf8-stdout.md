# Headless mode crashes at the config banner when stdout is not a UTF-8 console

**Status:** Open
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

## Fix direction

At the top of `cli_main` (or `run_cli`), reconfigure the streams once:

```python
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
```

`errors="replace"` keeps a stray unencodable byte from killing a 15-minute run. Pin with a test that runs the banner write through a cp1252-encoded stream. Note the same class of failure already bit the analysis tooling side (session-log sweeps tripping cp1252 on the 🔍 result emoji) — this is the product-side instance.

## Related

- `backlog/session-persistence-quadratic-io.md` — adjacent headless/session-log mechanics.
