"""ce-cursor: thin CE-compatible wrapper for Cursor; no native headless mode so run opens an interactive task file."""

from __future__ import annotations

from claude_efficient.cli.ce_wrapper_core import wrapper_main


def main() -> None:
    raise SystemExit(wrapper_main("cursor"))
