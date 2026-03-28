# src/claude_efficient/cli/init.py
from __future__ import annotations

import shutil
from pathlib import Path

import click

from claude_efficient.analysis.cache_health import CacheHealthMonitor
from claude_efficient.config.loader import resolve_helpers_config
from claude_efficient.generators.backends import HelperTask
from claude_efficient.generators.architecture import extract_architecture
from claude_efficient.generators.claude_md import ClaudeMdGenerator, write_claude_settings
from claude_efficient.generators.claudeignore import ClaudeignoreGenerator
from claude_efficient.generators.extractor import extract_facts
from claude_efficient.generators.orchestrator import invoke_helper
from claude_efficient.hooks.output_enforcer import write_enforcer_hooks


@click.command()
@click.option("--root", default=".", type=click.Path(), help="Project root")
@click.option("--force", is_flag=True, help="Overwrite existing CLAUDE.md")
@click.option("--reimport", is_flag=True, help="Regenerate @import subdirectory files only")
@click.option("--no-import-tree", is_flag=True, help="Skip subdirectory @import scaffolding")
@click.option(
    "--helpers",
    type=click.Choice(["off", "auto", "force"]),
    default=None,
    help="Helper mode override: off | auto | force",
)
@click.option(
    "--helper-backend",
    type=click.Choice(["auto", "gemini", "ollama", "opencode"]),
    default=None,
    help="Helper backend override",
)
def init(
    root: str,
    force: bool,
    reimport: bool,
    no_import_tree: bool,
    helpers: str | None,
    helper_backend: str | None,
) -> None:
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

    # ── 3. Resolve helper config ────────────────────────────────────────────
    try:
        mode, backend = resolve_helpers_config(helpers, helper_backend, root_path)
        click.secho(f"  ✓ Helper: mode={mode.value}, backend={backend.name}", fg="green")
    except Exception as e:
        click.secho(f"  ERROR: {e}", fg="red")
        raise SystemExit(1)

    # ── 4. CLAUDE.md ────────────────────────────────────────────────────────
    claude_md_path = root_path / "CLAUDE.md"
    gen = ClaudeMdGenerator()

    if reimport:
        click.echo("\n[ce] Regenerating @import tree...")
        facts = extract_facts(root_path)
        import_block = _build_import_block(root_path, gen, facts, mode, backend)
        if import_block:
            existing = claude_md_path.read_text(encoding="utf-8") if claude_md_path.exists() else ""
            if "## Subdirectory context" in existing:
                before = existing.split("## Subdirectory context")[0].rstrip()
                claude_md_path.write_text(before + import_block, encoding="utf-8")
            else:
                claude_md_path.write_text(existing + import_block, encoding="utf-8")
            click.secho("  ✓ @import tree updated", fg="green")
        else:
            click.echo("  No qualifying subdirectories found")
    elif claude_md_path.exists() and not force:
        click.echo("\n[ce] CLAUDE.md exists — skipping (--force to regenerate, --reimport for imports)")
    else:
        click.echo("\n[ce] Scanning codebase...")
        facts = extract_facts(root_path)

        click.echo("[ce] Extracting deep architecture...")
        arch = extract_architecture(root_path)

        # New hybrid approach: get LLM summary first
        response = invoke_helper(
            HelperTask.project_digest_root,
            gen.render_facts_to_prompt(facts),
            mode=mode,
            backend=backend
        )
        project_summary = response.text if not response.used_fallback else ""

        content = gen.generate_root(facts, project_summary, arch=arch)

        if not no_import_tree:
            import_block = _build_import_block(root_path, gen, facts, mode, backend)
            if import_block:
                content += import_block
                click.secho("  ✓ @import tree generated for qualifying subdirectories", fg="green")

        gen.write(root_path, content)
        gen.write_gemini_md(root_path, content)
        gen.write_agents_md(root_path, content)
        size = len(content.encode())
        click.secho(f"  ✓ CLAUDE.md generated ({size:,} bytes)", fg="green")
        click.secho(f"  ✓ GEMINI.md generated ({size:,} bytes)", fg="green")
        click.secho(f"  ✓ AGENTS.md generated ({size:,} bytes)", fg="green")

    # ── 5. .claudeignore ────────────────────────────────────────────────────
    click.echo("\n[ce] Generating ignore files...")
    ig_gen = ClaudeignoreGenerator()
    ig_gen.write(root_path, ig_gen.generate(root_path))
    click.secho("  ✓ .claudeignore + .geminiignore", fg="green")

    # ── 6. Hooks (PreCompact + output enforcer) ──────────────────────────
    click.echo("\n[ce] Writing hooks...")
    write_claude_settings(root_path)
    click.secho("  ✓ PreCompact hook — context survives /compact", fg="green")
    write_enforcer_hooks(root_path)
    click.secho("  ✓ Output enforcer — token discipline on every prompt", fg="green")

    # ── 7. Summary ──────────────────────────────────────────────────────────
    click.echo(f"\n{sep}")
    click.secho("[ce] Setup complete. Claude Code tokens used during init: 0", fg="cyan")
    click.echo("[ce] Next: ce run \"your first task\"")
    click.echo()


def _build_import_block(
    root_path: Path,
    gen: ClaudeMdGenerator,
    facts,
    mode,
    backend,
) -> str:
    qualifying = [c for c in facts.subdir_candidates if c.qualifies]
    if not qualifying:
        return ""
    import_lines = ["\n## Subdirectory context (auto-loaded by Claude Code)", ""]
    for candidate in qualifying[:5]:
        subdir_path = root_path / candidate.path
        subdir_path.mkdir(parents=True, exist_ok=True)
        response = invoke_helper(
            HelperTask.project_digest_subdir,
            gen.render_subdir_facts_to_prompt(candidate),
            mode=mode,
            backend=backend,
        )
        summary = response.text if not response.used_fallback else ""
        content = gen.generate_subdir(candidate, summary)
        (subdir_path / "CLAUDE.md").write_text(content, encoding="utf-8")
        (subdir_path / "GEMINI.md").write_text(content.replace("CLAUDE.md", "GEMINI.md"), encoding="utf-8")
        (subdir_path / "AGENTS.md").write_text(content.replace("CLAUDE.md", "AGENTS.md"), encoding="utf-8")
        import_lines.append(f"@{candidate.path}/CLAUDE.md")
    return "\n".join(import_lines)


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

    has_binary = shutil.which("claude-mem") is not None
    if has_binary:
        click.secho("  ⚠ claude-mem installed but worker not running on :37777", fg="yellow")
        click.secho("  Fix: claude-mem start  (or check github.com/thedotmack/claude-mem)", fg="yellow")
    else:
        click.secho("  ⚠ claude-mem not found — you're flying blind across sessions", fg="yellow")
        click.secho("  Fix: npm i -g claude-mem  (github.com/thedotmack/claude-mem)", fg="yellow")
        click.secho("  Without it: no cross-session memory, cold start every session", fg="yellow")
