"""ce-gemini: thin CE-compatible wrapper around Gemini CLI; headless mode uses `gemini -p`."""

from __future__ import annotations

from claude_efficient.cli.ce_wrapper_core import wrapper_main


def main() -> None:
    raise SystemExit(wrapper_main("gemini"))
