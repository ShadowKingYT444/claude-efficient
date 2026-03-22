# tests/test_session.py
"""Regression tests for `ce run` — primarily pipe-mode command shape."""
from __future__ import annotations

import json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from claude_efficient.cli.session import run
from claude_efficient.config.defaults import HelperMode
from claude_efficient.generators.backends import DeterministicBackend

_NO_BACKEND = (HelperMode.off, DeterministicBackend())


# ── fixtures / helpers ────────────────────────────────────────────────────────

def _mock_route(model: str = "claude-sonnet-4-6") -> MagicMock:
    m = MagicMock()
    m.model = model
    m.reason = "test"
    m.note = None
    return m


def _invoke(tmp_path: Path, args: list[str], extra_patches: dict | None = None):
    """Invoke `ce run` with all external calls mocked out."""
    (tmp_path / "CLAUDE.md").write_text("# test")
    runner = CliRunner()
    mock_route = _mock_route()

    with ExitStack() as stack:
        stack.enter_context(patch(
            "claude_efficient.cli.session.resolve_helpers_config",
            return_value=_NO_BACKEND,
        ))
        stack.enter_context(patch(
            "claude_efficient.cli.session.CacheHealthMonitor",
            return_value=MagicMock(check_all=MagicMock(
                return_value=MagicMock(risks=[])
            )),
        ))
        stack.enter_context(patch(
            "claude_efficient.cli.session.route", return_value=mock_route,
        ))
        stack.enter_context(patch(
            "claude_efficient.cli.session.SessionScopeAnalyzer",
            return_value=MagicMock(estimate=MagicMock(
                return_value=MagicMock(warning=None)
            )),
        ))
        stack.enter_context(patch(
            "claude_efficient.cli.session._read_enabled_mcps", return_value=[],
        ))
        stack.enter_context(patch(
            "claude_efficient.cli.session._fetch_mem_brief", return_value=None,
        ))
        mock_run = stack.enter_context(patch("subprocess.run"))

        result = runner.invoke(run, ["--root", str(tmp_path)] + args)

    return result, mock_run


# ── pipe-mode regression ──────────────────────────────────────────────────────

def test_pipe_mode_command_shape(tmp_path):
    """Regression: `-p` must produce exactly: claude --model <model> -p <prompt>."""
    result, mock_run = _invoke(tmp_path, ["-p", "fix the bug in auth.py"])

    assert result.exit_code == 0, result.output
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "claude"
    assert cmd[1] == "--model"
    assert cmd[3] == "-p"
    # No extra flags should be injected in default (non-telemetry) pipe mode
    assert len(cmd) == 5


def test_pipe_mode_prompt_position(tmp_path):
    """The prompt text must be the last element of the pipe command."""
    result, mock_run = _invoke(tmp_path, ["-p", "fix the bug in auth.py"])
    cmd = mock_run.call_args[0][0]
    # Final element is the (possibly optimized) prompt — never empty
    assert len(cmd[-1]) > 0


def test_pipe_mode_no_session_cache_flag(tmp_path):
    """Interactive mode must NOT include `-p` in the command."""
    result, mock_run = _invoke(tmp_path, ["fix the bug in auth.py"])
    cmd = mock_run.call_args[0][0]
    assert "-p" not in cmd


def test_interactive_mode_command_shape(tmp_path):
    """Interactive (default) mode: claude --model <model> <prompt>."""
    result, mock_run = _invoke(tmp_path, ["fix the bug in auth.py"])
    assert result.exit_code == 0, result.output
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "claude"
    assert cmd[1] == "--model"
    assert "-p" not in cmd
    assert len(cmd) == 4  # claude --model <model> <prompt>

def test_interactive_flag_without_task_starts_live_session(tmp_path):
    """--interactive allows a fully live claude session without TASK."""
    result, mock_run = _invoke(tmp_path, ["--interactive"])
    assert result.exit_code == 0, result.output
    cmd = mock_run.call_args[0][0]
    assert cmd == ["claude", "--model", "claude-sonnet-4-6"]

def test_missing_task_requires_interactive_flag(tmp_path):
    result, _ = _invoke(tmp_path, [])
    assert result.exit_code != 0
    assert "TASK is required unless --interactive is set." in result.output

def test_pipe_requires_task(tmp_path):
    result, _ = _invoke(tmp_path, ["-p"])
    assert result.exit_code != 0
    assert "TASK is required when using --pipe." in result.output


def test_pipe_model_override(tmp_path):
    """`--model` flag is honoured in pipe mode."""
    result, mock_run = _invoke(tmp_path, ["-p", "--model", "claude-opus-4-6", "task"])
    cmd = mock_run.call_args[0][0]
    assert cmd[2] == "claude-opus-4-6"


def test_dry_run_does_not_call_subprocess(tmp_path):
    """--dry-run must never invoke subprocess.run."""
    result, mock_run = _invoke(tmp_path, ["--dry-run", "fix bug in auth.py"])
    assert result.exit_code == 0
    mock_run.assert_not_called()


def test_dry_run_pipe_output_mentions_mode(tmp_path):
    result, _ = _invoke(tmp_path, ["--dry-run", "-p", "fix bug"])
    assert "PIPE" in result.output


def test_dry_run_interactive_output_mentions_mode(tmp_path):
    result, _ = _invoke(tmp_path, ["--dry-run", "fix bug"])
    assert "INTERACTIVE" in result.output


# ── telemetry flag ────────────────────────────────────────────────────────────

def test_telemetry_pipe_logs_to_file(tmp_path):
    """--telemetry in pipe mode writes a .ce-telemetry.jsonl record."""
    usage_json = json.dumps({
        "result": "done",
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 100,
            "cache_read_input_tokens": 800,
        },
    })
    (tmp_path / "CLAUDE.md").write_text("# test")
    runner = CliRunner()

    with ExitStack() as stack:
        stack.enter_context(patch(
            "claude_efficient.cli.session.resolve_helpers_config",
            return_value=_NO_BACKEND,
        ))
        stack.enter_context(patch(
            "claude_efficient.cli.session.CacheHealthMonitor",
            return_value=MagicMock(check_all=MagicMock(
                return_value=MagicMock(risks=[])
            )),
        ))
        stack.enter_context(patch(
            "claude_efficient.cli.session.route", return_value=_mock_route(),
        ))
        stack.enter_context(patch(
            "claude_efficient.cli.session.SessionScopeAnalyzer",
            return_value=MagicMock(estimate=MagicMock(
                return_value=MagicMock(warning=None)
            )),
        ))
        stack.enter_context(patch(
            "claude_efficient.cli.session._read_enabled_mcps", return_value=[],
        ))
        stack.enter_context(patch(
            "claude_efficient.cli.session._fetch_mem_brief", return_value=None,
        ))
        # Return mocked JSON usage from subprocess
        mock_proc = MagicMock()
        mock_proc.stdout = usage_json
        stack.enter_context(patch("subprocess.run", return_value=mock_proc))

        result = runner.invoke(run, [
            "--root", str(tmp_path), "-p", "--telemetry",
            "fix the bug in auth.py",
        ])

    assert result.exit_code == 0, result.output
    tel_file = tmp_path / ".ce-telemetry.jsonl"
    assert tel_file.exists(), "telemetry file not created"
    record = json.loads(tel_file.read_text().strip())
    assert record["mode"] == "pipe"
    assert record["actual_input_tokens"] == 1000
    assert record["actual_cache_read_tokens"] == 800
    assert record["baseline_input_tokens"] == 1800
    assert record["saved_input_tokens"] == 800
    assert abs(record["session_input_savings_pct"] - 44.4444) < 0.01
    assert record["meets_50pct_savings_target"] is False


def test_telemetry_pipe_command_adds_json_flag(tmp_path):
    """With --telemetry, pipe mode must add --output-format json to the command."""
    (tmp_path / "CLAUDE.md").write_text("# test")
    runner = CliRunner()

    captured_cmd: list[str] = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        m = MagicMock()
        m.stdout = json.dumps({"result": "ok", "usage": {}})
        return m

    with ExitStack() as stack:
        stack.enter_context(patch(
            "claude_efficient.cli.session.resolve_helpers_config",
            return_value=_NO_BACKEND,
        ))
        stack.enter_context(patch(
            "claude_efficient.cli.session.CacheHealthMonitor",
            return_value=MagicMock(check_all=MagicMock(
                return_value=MagicMock(risks=[])
            )),
        ))
        stack.enter_context(patch(
            "claude_efficient.cli.session.route", return_value=_mock_route(),
        ))
        stack.enter_context(patch(
            "claude_efficient.cli.session.SessionScopeAnalyzer",
            return_value=MagicMock(estimate=MagicMock(
                return_value=MagicMock(warning=None)
            )),
        ))
        stack.enter_context(patch(
            "claude_efficient.cli.session._read_enabled_mcps", return_value=[],
        ))
        stack.enter_context(patch(
            "claude_efficient.cli.session._fetch_mem_brief", return_value=None,
        ))
        stack.enter_context(patch("subprocess.run", side_effect=fake_run))
        runner.invoke(run, [
            "--root", str(tmp_path), "-p", "--telemetry", "fix bug in auth.py",
        ])

    assert "--output-format" in captured_cmd
    assert "json" in captured_cmd


def test_no_telemetry_flag_unchanged_pipe_command(tmp_path):
    """Without --telemetry, pipe command must be exactly 5 elements (regression guard)."""
    result, mock_run = _invoke(tmp_path, ["-p", "fix the bug in auth.py"])
    cmd = mock_run.call_args[0][0]
    assert "--output-format" not in cmd
    assert len(cmd) == 5


def test_run_filters_missing_experimental_flag_risk_when_session_env_sets_it(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# test")
    runner = CliRunner()
    mock_route = _mock_route()
    risk = MagicMock()
    risk.code = "missing_experimental_mcp_flag"
    risk.severity = "critical"
    risk.message = "missing flag"
    risk.fix = "set env"

    with ExitStack() as stack:
        stack.enter_context(patch(
            "claude_efficient.cli.session.resolve_helpers_config",
            return_value=_NO_BACKEND,
        ))
        stack.enter_context(patch(
            "claude_efficient.cli.session.CacheHealthMonitor",
            return_value=MagicMock(check_all=MagicMock(
                return_value=MagicMock(risks=[risk])
            )),
        ))
        stack.enter_context(patch(
            "claude_efficient.cli.session.route", return_value=mock_route,
        ))
        stack.enter_context(patch(
            "claude_efficient.cli.session.SessionScopeAnalyzer",
            return_value=MagicMock(estimate=MagicMock(
                return_value=MagicMock(warning=None)
            )),
        ))
        stack.enter_context(patch(
            "claude_efficient.cli.session._read_enabled_mcps", return_value=[],
        ))
        stack.enter_context(patch(
            "claude_efficient.cli.session._fetch_mem_brief", return_value=None,
        ))
        mock_run = stack.enter_context(patch("subprocess.run"))

        result = runner.invoke(run, ["--root", str(tmp_path), "fix the bug in auth.py"])

    assert result.exit_code == 0, result.output
    assert "missing flag" not in result.output
    mock_run.assert_called_once()
