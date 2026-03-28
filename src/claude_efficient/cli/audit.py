from __future__ import annotations

import json
from pathlib import Path

import click

from claude_efficient.analysis.waste_detector import WasteDetector

SEVERITY_COLORS = {
    "critical": "red",
    "high": "yellow",
    "medium": "cyan",
    "low": "white",
}


@click.command()
@click.argument("transcript", required=False, type=click.Path())
@click.option("--json", "output_json", is_flag=True)
def audit(transcript: str | None, output_json: bool) -> None:
    """Analyze a session transcript for token waste and cache violations."""
    if transcript is None:
        click.echo("[ce] No transcript provided. Pass a session file path.")
        click.echo("[ce] Save a session: ce run 'task' > session.log 2>&1")
        return

    run_audit_report(transcript, output_json)


def run_audit_report(transcript: str, output_json: bool = False) -> None:
    path = Path(transcript)
    if not path.exists():
        click.secho(f"[ce] ERROR: File not found: {path}", fg="red")
        raise SystemExit(1)

    report = WasteDetector().run(path)

    if output_json:
        click.echo(json.dumps({
            "waste_pct": report.waste_pct,
            "total_tokens": report.total_tokens,
            "findings": [vars(f) for f in report.findings],
        }, indent=2))
        return

    click.echo(f"\nclaude-efficient audit — {path.name}")
    click.echo("─" * 50)
    click.echo(f"Estimated waste: {report.waste_pct:.0%} of session\n")

    for i, f in enumerate(report.findings, 1):
        color = SEVERITY_COLORS.get(f.severity, "white")
        click.secho(
            f"PRIORITY {i}  │ {f.category:<30} │ ~{f.tokens_wasted:,} tokens",
            fg=color,
        )
        click.echo(f"  Fix: {f.fix}")
        for ev in f.evidence[:2]:
            click.echo(f"  Evidence: {ev}")
        click.echo()

    if not report.findings:
        click.secho("No waste patterns detected — session looks clean.", fg="green")
    elif report.findings[0].severity in ("critical", "high"):
        click.secho(
            "Run `ce init` to address PRIORITY 1. "
            "Fix cache_invalidation issues before anything else.",
            fg="green",
        )
