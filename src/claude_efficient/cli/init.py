# src/claude_efficient/cli/init.py
from __future__ import annotations

import shutil
from pathlib import Path

import click

from claude_efficient.analysis.cache_health import CacheHealthMonitor
from claude_efficient.generators.backends import detect_backend
from claude_efficient.generators.claude_md import ClaudeMdGenerator, write_claude_settings
from claude_efficient.generators.claudeignore import ClaudeignoreGenerator


@click.command()
@click.option("--root", default=".", type=click.Path(), help="Project root")
@click.option("--force", is_flag=True, help="Overwrite existing CLAUDE.md")
@click.option("--reimport", is_flag=True, help="Regenerate @import subdirectory files only")
@click.option("--no-import-tree", is_flag=True, help="Skip subdirectory @import scaffolding")
def init(root: str, force: bool, reimport: bool, no_import_tree: bool) -> None:
    """One-time project setup: CLAUDE.md, .claudeignore, PreCompact hook, cache health check."""
    root_path = Path(root).resolve()
    sep = "─" * 50

    click.echo(f"\n[ce] Initializing {root_path.name}/")
    click.echo(sep)

    # ── 1. claude-mem health check ──────────────────────────────────────────
    _check_claude_mem()

    # ── 2. Cache health pre-flight ──────────────────────────────────────────
    click.echo("\n[ce] Cache health check...")
    report = CacheHealthMonitor().check_all(root_path)
    for risk in report.risks:
        color = "red" if risk.severity == "critical" else "yellow"
        click.secho(f"  [{risk.severity.upper()}] {risk.message}", fg=color)
        click.secho(f"  Fix: {risk.fix}\n", fg=color)
    if report.is_healthy:
        click.secho("  ✓ No cache risks detected", fg="green")

    # ── 3. Backend detection ────────────────────────────────────────────────
    click.echo("\n[ce] Detecting analysis backend...")
    try:
        backend = detect_backend()
        click.secho(f"  ✓ {backend.name} selected (analysis cost: $0.00)", fg="green")
    except RuntimeError as e:
        click.secho(f"  ERROR: {e}", fg="red")
        raise SystemExit(1)

    # ── 4. CLAUDE.md ────────────────────────────────────────────────────────
    claude_md_path = root_path / "CLAUDE.md"
    gen = ClaudeMdGenerator()

    if reimport:
        # Just regenerate subdirectory imports, don't touch root
        click.echo("\n[ce] Regenerating @import tree...")
        import_block = gen.generate_import_tree(root_path, backend)
        if import_block:
            existing = claude_md_path.read_text() if claude_md_path.exists() else ""
            # Replace existing import block or append
            if "## Subdirectory context" in existing:
                before = existing.split("## Subdirectory context")[0].rstrip()
                claude_md_path.write_text(before + import_block, encoding="utf-8")
            else:
                claude_md_path.write_text(existing + import_block, encoding="utf-8")
            click.secho("  ✓ @import tree updated", fg="green")
        else:
            click.echo("  No qualifying subdirectories found (need ≥3 .py files each)")
    elif claude_md_path.exists() and not force:
        click.echo("\n[ce] CLAUDE.md exists — skipping (--force to regenerate, --reimport for imports)")
    else:
        click.echo("\n[ce] Scanning codebase...")
        content = gen.generate(root_path, backend)

        # Append @import tree if subdirs qualify
        if not no_import_tree:
            import_block = gen.generate_import_tree(root_path, backend)
            if import_block:
                content += import_block
                click.secho("  ✓ @import tree generated for qualifying subdirectories", fg="green")

        gen.write(root_path, content)
        gen.write_gemini_md(root_path, content)
        size = len(content.encode())
        click.secho(f"  ✓ CLAUDE.md generated ({size:,} bytes)", fg="green")
        click.secho(f"  ✓ GEMINI.md generated ({size:,} bytes)", fg="green")

    # ── 5. .claudeignore ────────────────────────────────────────────────────
    click.echo("\n[ce] Generating ignore files...")
    ig_gen = ClaudeignoreGenerator()
    ig_gen.write(root_path, ig_gen.generate(root_path))
    click.secho("  ✓ .claudeignore + .geminiignore", fg="green")

    # ── 6. PreCompact hook ──────────────────────────────────────────────────
    click.echo("\n[ce] Writing PreCompact hook...")
    settings_path = write_claude_settings(root_path)
    click.secho(f"  ✓ {settings_path.relative_to(root_path)} — context survives /compact", fg="green")

    # ── 7. Summary ──────────────────────────────────────────────────────────
    click.echo(f"\n{sep}")
    click.secho("[ce] Setup complete. Claude Code tokens used: 0", fg="cyan")
    click.echo("[ce] Next: ce run \"your first task\"")
    click.echo()


# ── helpers ─────────────────────────────────────────────────────────────────

def _check_claude_mem() -> None:
    """Verify claude-mem worker is reachable. Warn loudly if not."""
    click.echo("\n[ce] Checking claude-mem...")
    try:
        import requests
        r = requests.get("http://localhost:37777/health", timeout=2)
        if r.ok:
            click.secho("  ✓ claude-mem worker running", fg="green")
            return
    except Exception:
        pass

    # Check if it's installed at all
    has_binary = shutil.which("claude-mem") is not None
    if has_binary:
        click.secho("  ⚠ claude-mem installed but worker not running on :37777", fg="yellow")
        click.secho("  Fix: claude-mem start  (or check github.com/thedotmack/claude-mem)", fg="yellow")
    else:
        click.secho("  ⚠ claude-mem not found — you're flying blind across sessions", fg="yellow")
        click.secho("  Fix: npm i -g claude-mem  (github.com/thedotmack/claude-mem)", fg="yellow")
        click.secho("  Without it: no cross-session memory, cold start every session", fg="yellow")
