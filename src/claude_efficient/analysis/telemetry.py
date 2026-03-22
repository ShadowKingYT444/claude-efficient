# src/claude_efficient/analysis/telemetry.py
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

_TELEMETRY_FILE = ".ce-telemetry.jsonl"


@dataclass
class TelemetryRecord:
    timestamp: str
    mode: str               # "pipe" | "interactive"
    model: str
    prompt_chars_original: int
    prompt_chars_optimized: int
    chars_saved: int
    # Populated in pipe+telemetry mode via --output-format json
    actual_input_tokens: int | None = None
    actual_output_tokens: int | None = None
    actual_cache_read_tokens: int | None = None
    baseline_input_tokens: int | None = None
    saved_input_tokens: int | None = None
    session_input_savings_pct: float | None = None
    meets_50pct_savings_target: bool | None = None
    session_duration_s: float | None = None


@dataclass
class SavingsVerification:
    threshold_pct: float
    sessions_evaluated: int
    sessions_passing: int
    sessions_failing: int
    failing_session_indexes: list[int]


def get_global_telemetry_path() -> Path:
    p = Path.home() / ".ce-telemetry.jsonl"
    return p

def record(path: Path, rec: TelemetryRecord) -> None:
    """Append one record to <path>/.ce-telemetry.jsonl and globally."""
    line = json.dumps(asdict(rec)) + "\n"
    # Write local
    try:
        with open(path / _TELEMETRY_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    # Write global
    try:
        with open(get_global_telemetry_path(), "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass

def load(path: Path | None = None) -> list[TelemetryRecord]:
    if path is None:
        tel = get_global_telemetry_path()
    else:
        tel = path / _TELEMETRY_FILE
    if not tel.exists():
        return []
    records: list[TelemetryRecord] = []
    for line in tel.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                records.append(TelemetryRecord(**json.loads(line)))
            except Exception:
                pass
    return records


def estimate_baseline_input_tokens(
    actual_input_tokens: int | None,
    actual_cache_read_tokens: int | None,
) -> int | None:
    """Estimated no-cache input baseline = billed input + cache-read input."""
    if actual_input_tokens is None or actual_cache_read_tokens is None:
        return None
    baseline = actual_input_tokens + actual_cache_read_tokens
    return baseline if baseline > 0 else None


def estimate_session_input_savings_pct(
    actual_input_tokens: int | None,
    actual_cache_read_tokens: int | None,
) -> float | None:
    baseline = estimate_baseline_input_tokens(actual_input_tokens, actual_cache_read_tokens)
    if baseline is None:
        return None
    return (actual_cache_read_tokens / baseline) * 100.0


def _session_input_savings_pct(record: TelemetryRecord) -> float | None:
    if record.session_input_savings_pct is not None:
        return record.session_input_savings_pct
    return estimate_session_input_savings_pct(
        record.actual_input_tokens,
        record.actual_cache_read_tokens,
    )


def verify_records_min_session_savings(
    records: list[TelemetryRecord],
    threshold_pct: float = 50.0,
) -> SavingsVerification:
    sessions_evaluated = 0
    sessions_passing = 0
    failing_session_indexes: list[int] = []

    for index, record in enumerate(records, start=1):
        pct = _session_input_savings_pct(record)
        if pct is None:
            continue
        sessions_evaluated += 1
        if pct >= threshold_pct:
            sessions_passing += 1
        else:
            failing_session_indexes.append(index)

    return SavingsVerification(
        threshold_pct=threshold_pct,
        sessions_evaluated=sessions_evaluated,
        sessions_passing=sessions_passing,
        sessions_failing=sessions_evaluated - sessions_passing,
        failing_session_indexes=failing_session_indexes,
    )


def verify_min_session_savings(
    path: Path,
    threshold_pct: float = 50.0,
) -> SavingsVerification:
    return verify_records_min_session_savings(load(path), threshold_pct=threshold_pct)


def summarize(path: Path) -> str:
    records = load(path)
    if not records:
        return "No telemetry yet. Run `ce run` to start collecting."

    n = len(records)
    total_chars_saved = sum(r.chars_saved for r in records)
    pipe_with_usage = [
        r
        for r in records
        if r.mode == "pipe" and r.actual_input_tokens is not None
    ]

    lines = [f"Telemetry: {n} session(s) recorded"]
    lines.append(f"  Prompt chars saved (optimizer): {total_chars_saved:,}")

    if pipe_with_usage:
        avg_in = sum(r.actual_input_tokens for r in pipe_with_usage) / len(pipe_with_usage)  # type: ignore[arg-type]
        avg_cache = sum((r.actual_cache_read_tokens or 0) for r in pipe_with_usage) / len(pipe_with_usage)
        cache_pct = (avg_cache / avg_in * 100) if avg_in > 0 else 0.0
        lines.append(f"  Avg input tokens  (pipe): {avg_in:.0f}")
        lines.append(f"  Avg cache-read    (pipe): {avg_cache:.0f}  ({cache_pct:.1f}% hit rate)")

        verification = verify_records_min_session_savings(records, threshold_pct=50.0)
        if verification.sessions_evaluated > 0:
            avg_savings_pct = (
                sum(
                    pct
                    for pct in (_session_input_savings_pct(record) for record in records)
                    if pct is not None
                )
                / verification.sessions_evaluated
            )
            lines.append(
                "  Session savings vs no-cache baseline (baseline=input+cache-read):"
            )
            lines.append(f"    Avg savings: {avg_savings_pct:.1f}%")
            lines.append(
                f"    >=50% target met: {verification.sessions_passing}/{verification.sessions_evaluated}"
            )
            if verification.sessions_failing:
                failing = ", ".join(
                    f"#{idx}" for idx in verification.failing_session_indexes[:5]
                )
                lines.append(f"    Failing sessions: {failing}")
        else:
            lines.append(
                "  Session savings verification unavailable (missing input/cache token usage in records)."
            )

    interactive = [r for r in records if r.mode == "interactive" and r.session_duration_s]
    if interactive:
        avg_dur = sum(r.session_duration_s for r in interactive) / len(interactive)  # type: ignore[arg-type]
        lines.append(f"  Avg session duration (interactive): {avg_dur:.1f}s")

    return "\n".join(lines)
