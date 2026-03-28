from click.testing import CliRunner
from claude_efficient.cli.main import cli


def test_help_exits_zero():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0


def test_subcommands_present():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert "init" in result.output
    assert "run" in result.output
    assert "gains" in result.output


def test_verbose_shows_hidden_commands():
    runner = CliRunner()
    result = runner.invoke(cli, ["--verbose", "--help"])
    assert "audit" in result.output


def test_init_runs():
    runner = CliRunner()
    result = runner.invoke(cli, ["init"])
    assert result.exit_code == 0
    assert "Initializing" in result.output
