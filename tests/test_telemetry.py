from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from claude_efficient.analysis.telemetry import (
    TelemetryRecord,
    record as telemetry_record,
    summarize,
    verify_min_session_savings,
)
from claude_efficient.cli.commands import telemetry


def _append_pipe_record(
    root: Path,
    *,
    input_tokens: int,
    cache_read_tokens: int,
) -> None:
    telemetry_record(
        root,
        TelemetryRecord(
            timestamp="2026-03-22T00:00:00",
            mode="pipe",
            model="claude-sonnet-4-6",
            prompt_chars_original=120,
            prompt_chars_optimized=100,
            chars_saved=20,
            actual_input_tokens=input_tokens,
            actual_output_tokens=120,
            actual_cache_read_tokens=cache_read_tokens,
        ),
    )


def test_verify_min_session_savings_counts_passes_and_failures(tmp_path):
    _append_pipe_record(tmp_path, input_tokens=1_000, cache_read_tokens=1_500)  # 60%
    _append_pipe_record(tmp_path, input_tokens=900, cache_read_tokens=300)      # 25%

    verification = verify_min_session_savings(tmp_path, threshold_pct=50.0)

    assert verification.sessions_evaluated == 2
    assert verification.sessions_passing == 1
    assert verification.sessions_failing == 1
    assert verification.failing_session_indexes == [2]


def test_summarize_includes_session_target_verification_details(tmp_path):
    _append_pipe_record(tmp_path, input_tokens=1_000, cache_read_tokens=1_500)  # 60%
    _append_pipe_record(tmp_path, input_tokens=900, cache_read_tokens=300)      # 25%

    summary = summarize(tmp_path)

    assert "Session savings vs no-cache baseline" in summary
    assert ">=50% target met: 1/2" in summary
    assert "Failing sessions: #2" in summary


def test_telemetry_command_verification_fails_when_threshold_not_met(tmp_path):
    _append_pipe_record(tmp_path, input_tokens=1_000, cache_read_tokens=400)  # 28.6%
    runner = CliRunner()

    result = runner.invoke(
        telemetry,
        ["--root", str(tmp_path), "--verify-min-savings-pct", "50"],
    )

    assert result.exit_code != 0
    assert "below 50.0% savings" in result.output


def test_telemetry_command_verification_passes_when_threshold_met(tmp_path):
    _append_pipe_record(tmp_path, input_tokens=500, cache_read_tokens=700)  # 58.3%
    _append_pipe_record(tmp_path, input_tokens=1_200, cache_read_tokens=1_400)  # 53.8%
    runner = CliRunner()

    result = runner.invoke(
        telemetry,
        ["--root", str(tmp_path), "--verify-min-savings-pct", "50"],
    )

    assert result.exit_code == 0, result.output
    assert "Verification passed" in result.output
