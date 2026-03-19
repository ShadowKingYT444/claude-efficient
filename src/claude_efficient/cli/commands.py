from __future__ import annotations

from pathlib import Path

import click


@click.command("mem-search")
@click.argument("query")
@click.option("--limit", default=5, show_default=True)
def mem_search(query: str, limit: int) -> None:
    """Search claude-mem for context from prior sessions before starting a task."""
    try:
        import requests
        r = requests.post(
            "http://localhost:37777/search",
            json={"query": query, "limit": limit},
            timeout=5,
        )
        if not r.ok:
            click.secho(f"[ce] claude-mem returned {r.status_code}", fg="red")
            return
        results = r.json().get("results", [])
        if not results:
            click.echo("[ce] No relevant prior context found.")
            return
        click.echo(f"\n[ce] Top {len(results)} results for: {query!r}\n")
        for i, res in enumerate(results, 1):
            ts = res.get("timestamp", "")[:10]
            summary = res.get("summary", "(no summary)")
            click.echo(f"  {i}. [{ts}] {summary}")
    except Exception as e:
        click.secho(f"[ce] claude-mem unavailable: {e}", fg="yellow")
        click.echo("[ce] Is the worker running? Try: claude-mem start")


@click.command("scope-check")
@click.argument("task")
@click.option("--root", default=".", type=click.Path())
def scope_check(task: str, root: str) -> None:
    """Estimate token requirements for a task before committing to a session."""
    from claude_efficient.session.compact_manager import SessionScopeAnalyzer

    root_path = Path(root).resolve()
    est = SessionScopeAnalyzer().estimate(task, root_path)

    click.echo(f"\n[ce] Scope estimate for: {task[:60]!r}")
    click.echo("─" * 50)
    click.echo(f"  Estimated tokens:    ~{est.estimated_tokens:,}")
    click.echo(f"  Needs compact cycle: {'yes ⚠' if est.will_require_compact else 'no ✓'}")
    if est.warning:
        click.secho(f"\n  ⚠ {est.warning}", fg="yellow")
        click.secho(f"  → {est.recommendation}", fg="yellow")
    else:
        click.secho(f"\n  ✓ {est.recommendation}", fg="green")


@click.command()
@click.option("--root", default=".", type=click.Path())
def status(root: str) -> None:
    """Show project health: cache risks, CLAUDE.md size, claude-mem status."""
    from claude_efficient.analysis.cache_health import CacheHealthMonitor

    root_path = Path(root).resolve()
    click.echo(f"\n[ce] Status — {root_path.name}/")
    click.echo("─" * 50)

    # CLAUDE.md
    claude_md = root_path / "CLAUDE.md"
    if claude_md.exists():
        size = len(claude_md.read_bytes())
        color = "green" if size <= 2_000 else "yellow" if size <= 4_000 else "red"
        flag = "✓" if size <= 2_000 else "⚠ over 2KB target" if size <= 4_000 else "✗ over 4KB — instruction-following degraded"
        click.secho(f"  CLAUDE.md:  {size:,} bytes {flag}", fg=color)
    else:
        click.secho("  CLAUDE.md:  MISSING — run `ce init`", fg="red")

    # .claudeignore
    if (root_path / ".claudeignore").exists():
        click.secho("  .claudeignore: ✓", fg="green")
    else:
        click.secho("  .claudeignore: MISSING", fg="yellow")

    # PreCompact hook
    settings = root_path / ".claude" / "settings.json"
    if settings.exists():
        import json
        try:
            data = json.loads(settings.read_text())
            has_hook = "PreCompact" in data.get("hooks", {})
            color = "green" if has_hook else "yellow"
            flag = "✓" if has_hook else "MISSING — run `ce init`"
            click.secho(f"  PreCompact hook: {flag}", fg=color)
        except Exception:
            click.secho("  PreCompact hook: parse error in settings.json", fg="yellow")
    else:
        click.secho("  PreCompact hook: MISSING — run `ce init`", fg="yellow")

    # Cache health
    click.echo("\n  Cache risks:")
    report = CacheHealthMonitor().check_all(root_path)
    if report.is_healthy:
        click.secho("    ✓ None detected", fg="green")
    else:
        for risk in report.risks:
            color = "red" if risk.severity == "critical" else "yellow"
            click.secho(f"    [{risk.severity.upper()}] {risk.message}", fg=color)

    # claude-mem
    click.echo("\n  claude-mem:")
    try:
        import requests
        r = requests.get("http://localhost:37777/health", timeout=2)
        if r.ok:
            click.secho("    ✓ Worker running on :37777", fg="green")
        else:
            click.secho("    ⚠ Worker reachable but unhealthy", fg="yellow")
    except Exception:
        click.secho("    ✗ Worker not running — cross-session memory disabled", fg="red")
        click.echo("      Fix: claude-mem start")
