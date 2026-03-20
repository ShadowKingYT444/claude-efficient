"""ce-opencode: thin CE-compatible wrapper around OpenCode CLI; headless mode uses `opencode run`."""

from __future__ import annotations

from claude_efficient.cli.ce_wrapper_core import wrapper_main


def main() -> None:
    raise SystemExit(wrapper_main("opencode"))
