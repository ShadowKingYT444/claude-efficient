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
    session_duration_s: float | None = None


def record(path: Path, rec: TelemetryRecord) -> None:
    """Append one record to <path>/.ce-telemetry.jsonl."""
    with open(path / _TELEMETRY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(rec)) + "\n")


def load(path: Path) -> list[TelemetryRecord]:
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


def summarize(path: Path) -> str:
    records = load(path)
    if not records:
        return "No telemetry yet. Run `ce run --telemetry` to start collecting."

    n = len(records)
    total_chars_saved = sum(r.chars_saved for r in records)
    pipe_with_usage = [
        r for r in records
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

    interactive = [r for r in records if r.mode == "interactive" and r.session_duration_s]
    if interactive:
        avg_dur = sum(r.session_duration_s for r in interactive) / len(interactive)  # type: ignore[arg-type]
        lines.append(f"  Avg session duration (interactive): {avg_dur:.1f}s")

    return "\n".join(lines)
