"""ce-codex: thin CE-compatible wrapper around Codex CLI; headless mode uses `codex exec`."""

from __future__ import annotations

from claude_efficient.cli.ce_wrapper_core import wrapper_main


def main() -> None:
    raise SystemExit(wrapper_main("codex"))
