# src/claude_efficient/cli/session.py
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click

from claude_efficient.analysis.cache_health import CacheHealthMonitor
from claude_efficient.prompt.optimizer import optimize
from claude_efficient.session.compact_manager import SessionScopeAnalyzer
from claude_efficient.session.mcp_config import McpConfigAdvisor
from claude_efficient.session.model_router import route


@click.command()
@click.argument("task")
@click.option("--root", default=".", type=click.Path())
@click.option("--model", default=None, help="Override auto model routing")
@click.option("--no-health-check", is_flag=True, help="Skip cache health pre-flight")
@click.option("--dry-run", is_flag=True, help="Show plan without executing")
def run(
    task: str,
    root: str,
    model: str | None,
    no_health_check: bool,
    dry_run: bool,
) -> None:
    """Optimized session wrapper for a Claude Code task."""
    root_path = Path(root).resolve()
    sep = "─" * 50

    # ── 1. Cache health pre-flight ───────────────────────────────────────────
    if not no_health_check:
        report = CacheHealthMonitor().check_all(root_path)
        for risk in report.risks:
            color = "red" if risk.severity == "critical" else "yellow"
            click.secho(f"[ce] [{risk.severity.upper()}] {risk.message}", fg=color)
            if risk.severity == "critical" and not dry_run:
                click.secho(f"[ce] Fix: {risk.fix}", fg=color)
                if not click.confirm("[ce] Continue anyway?", default=False):
                    raise SystemExit(0)

    # ── 2. Prompt optimization ───────────────────────────────────────────────
    opt = optimize(task)
    for warning in opt.warnings:
        click.secho(f"[ce] ⚠ {warning}", fg="yellow")
    if opt.chars_saved > 0:
        click.echo(f"[ce] Prompt: -{opt.chars_saved} chars after optimization")

    # ── 3. Session scope estimate ────────────────────────────────────────────
    scope = SessionScopeAnalyzer().estimate(opt.text, root_path)
    if scope.warning:
        click.secho(f"[ce] ⚠ Scope: {scope.warning}", fg="yellow")
        click.echo(f"[ce]   → {scope.recommendation}")

    # ── 4. Model selection (session-start only, never changes) ───────────────
    decision = route(opt.text) if model is None else None
    chosen_model = model or decision.model
    reason = f" ({decision.reason})" if decision else " (manual override)"
    click.echo(f"[ce] Model: {chosen_model}{reason}")
    if decision and decision.note:
        click.echo(f"[ce]   {decision.note}")

    # ── 5. MCP advisory (informational only — no server changes) ────────────
    enabled_mcps = _read_enabled_mcps(root_path)
    if enabled_mcps:
        plan = McpConfigAdvisor().plan_session(opt.text, enabled_mcps, root_path)
        for advice in plan.advice:
            click.secho(f"[ce] MCP: {advice}", fg="cyan")

    # ── 6. claude-mem session brief ──────────────────────────────────────────
    brief = _fetch_mem_brief(opt.text)
    if brief:
        click.echo(f"[ce] Memory: {brief}")

    # ── 7. Build command ─────────────────────────────────────────────────────
    final_prompt = opt.text
    if brief:
        final_prompt = f"[Session context from prior work: {brief}]\n\n{opt.text}"

    cmd = ["claude", "--model", chosen_model, "-p", final_prompt]

    if dry_run:
        click.secho(f"\n{sep}", fg="cyan")
        click.secho("[ce] DRY RUN — would execute:", fg="cyan")
        click.echo(f"  claude --model {chosen_model} -p <optimized_prompt>")
        click.echo(f"  Prompt length: {len(final_prompt)} chars")
        return

    # ── 8. Execute ────────────────────────────────────────────────────────────
    click.secho(f"\n[ce] Running on {chosen_model}...\n", fg="cyan")
    subprocess.run(cmd, cwd=root_path, shell=(sys.platform == "win32"))


# ── helpers ──────────────────────────────────────────────────────────────────

def _read_enabled_mcps(root: Path) -> list[str]:
    config_file = root / ".claude-efficient.toml"
    if not config_file.exists():
        return []
    try:
        import tomllib
        with open(config_file, "rb") as f:
            return tomllib.load(f).get("mcp", {}).get("enabled_servers", [])
    except Exception:
        return []


def _fetch_mem_brief(task: str, max_chars: int = 300) -> str | None:
    """
    Query claude-mem for relevant context from prior sessions.
    Returns a compact brief string or None if claude-mem is unavailable.
    ~150-300 tokens versus 2,000+ for a full TASKS.md paste.
    """
    try:
        import requests
        r = requests.post(
            "http://localhost:37777/search",
            json={"query": task, "limit": 3},
            timeout=3,
        )
        if not r.ok:
            return None
        results = r.json().get("results", [])
        if not results:
            return None
        # Compact: join top results into one line
        snippets = [res.get("summary", "")[:80] for res in results[:3] if res.get("summary")]
        brief = " | ".join(snippets)
        return brief[:max_chars] if brief else None
    except Exception:
        return None
