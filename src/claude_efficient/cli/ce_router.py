"""ce-router: delegates `--cli <name> --cmd <init|run|status>` calls to CE-compatible CLI wrappers."""

from __future__ import annotations

from claude_efficient.cli.ce_wrapper_core import router_main


def main() -> None:
    raise SystemExit(router_main())
