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


class VerboseGroup(click.Group):
    """Click group that hides internal commands unless --verbose is passed."""

    _verbose = False

    def list_commands(self, ctx: click.Context) -> list[str]:
        internal = ["audit", "helpers", "mem-search", "scope-check", "status", "telemetry"]
        for name in internal:
            if name in self.commands:
                self.commands[name].hidden = not self._verbose
        if self._verbose:
            return sorted(self.commands.keys())
        return ["init", "run", "gains"]

    def get_command(self, ctx: click.Context, name: str) -> click.Command | None:
        return self.commands.get(name)


def _set_verbose(ctx: click.Context, _param: click.Parameter, value: bool) -> bool:
    VerboseGroup._verbose = value
    return value


@click.group(cls=VerboseGroup, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="ce-tool")
@click.option(
    "--verbose", "-v", is_flag=True, is_eager=True,
    expose_value=True, callback=_set_verbose,
    help="Show internal debugging commands.",
)
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """claude-efficient — token optimization for Claude Code sessions."""
    ctx.ensure_object(dict)
    ctx.obj["VERBOSE"] = verbose


# Core commands
cli.add_command(init)
cli.add_command(run)
cli.add_command(gains)

# Internal/hidden commands
cli.add_command(audit)
cli.add_command(helpers_cmd, "helpers")
cli.add_command(mem_search)
cli.add_command(scope_check)
cli.add_command(status)
cli.add_command(telemetry)


if __name__ == "__main__":
    cli()
