"""
Regression tests for bugs/headless-banner-crash-nonutf8-stdout.md.

With stdout redirected (pipe, > file, CI capture), Windows Python falls back
to the locale encoding (cp1252); the headless config banner's warning emoji
raises UnicodeEncodeError and kills the run before the agent starts
(live crash 2026-10-07, background-task capture).
"""

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.tui import _ensure_utf8_streams


def test_emoji_writable_after_reconfigure():
    buf = io.BytesIO()
    wrapper = io.TextIOWrapper(buf, encoding="cp1252")  # simulate redirected stdout
    real = sys.stdout
    sys.stdout = wrapper
    try:
        _ensure_utf8_streams()
        sys.stdout.write("⚠️ AUTO-APPROVE")  # the banner's warning emoji
        sys.stdout.flush()
    finally:
        sys.stdout = real
    assert b"\xe2\x9a\xa0" in buf.getvalue(), "banner emoji must encode as UTF-8 bytes"


def test_unencodable_bytes_do_not_raise():
    buf = io.BytesIO()
    wrapper = io.TextIOWrapper(buf, encoding="cp1252")
    real = sys.stderr
    sys.stderr = wrapper
    try:
        _ensure_utf8_streams()
        sys.stderr.write("ok \udcff")  # lone surrogate: unencodable even in utf-8
        sys.stderr.flush()
    finally:
        sys.stderr = real
    assert b"ok" in buf.getvalue()


def test_cli_main_calls_the_guard():
    import ast
    tree = ast.parse((Path(__file__).parent.parent / "src" / "engine" / "tui.py").read_text(encoding="utf-8"))
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "cli_main"
    )
    assert "_ensure_utf8_streams" in ast.dump(fn), "cli_main must reconfigure streams at entry"
