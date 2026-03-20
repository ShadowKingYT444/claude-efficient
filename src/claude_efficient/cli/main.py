# src/claude_efficient/cli/main.py
import sys

import click

# Ensure UTF-8 output on Windows (box-drawing chars, checkmarks, etc.)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

from claude_efficient.cli.audit import audit
from claude_efficient.cli.commands import mem_search, scope_check, status, telemetry
from claude_efficient.cli.gains import gains
from claude_efficient.cli.helpers import helpers_cmd
from claude_efficient.cli.init import init
from claude_efficient.cli.session import run


@click.group()
@click.version_option(package_name="claude-efficient")
def cli() -> None:
    """claude-efficient — token optimization for Claude Code sessions."""


cli.add_command(init)
cli.add_command(run)
cli.add_command(audit)
cli.add_command(gains)
cli.add_command(helpers_cmd, "helpers")
cli.add_command(mem_search)
cli.add_command(scope_check)
cli.add_command(status)
cli.add_command(telemetry)

if __name__ == "__main__":
    cli()
