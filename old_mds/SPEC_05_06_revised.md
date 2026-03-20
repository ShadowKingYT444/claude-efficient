# SPEC_05 — `analysis/cache_health.py`
**Session goal:** Prompt cache health monitor. Detects violations before they happen.
**Model:** Sonnet. **Est. context:** Small. **Clear after:** yes.
**Reads:** `CLAUDE.md` only.

---

## Context

Prompt caching is why Claude Code is economically viable. Without cache hits, a long
Opus session costs $50–100 in input tokens; with them, $10–19. The prefix must stay
byte-identical every turn. Two things kill it silently: model switches mid-session and
MCP server removal mid-session.

`ENABLE_EXPERIMENTAL_MCP_CLI=true` loads MCP tool schemas on-demand instead of upfront —
this is the native solution to MCP token overhead. A user with 15 MCP servers and this
flag unset burns 40–105k tokens before typing a word.

---

## Full implementation

```python
# src/claude_efficient/analysis/cache_health.py
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CacheRisk:
    severity: str          # "critical" | "warning" | "info"
    code: str              # machine-readable key
    message: str
    fix: str


@dataclass
class CacheHealthReport:
    risks: list[CacheRisk] = field(default_factory=list)

    @property
    def has_critical(self) -> bool:
        return any(r.severity == "critical" for r in self.risks)

    @property
    def is_healthy(self) -> bool:
        return not self.risks


class CacheHealthMonitor:
    """
    Static pre-session checks. Run before launching claude to catch
    configuration mistakes that invalidate prompt caching.
    """

    # Known session token overhead per unflagged MCP server schema
    TOKENS_PER_MCP_SERVER = 1_200

    def check_all(self, root: Path = Path(".")) -> CacheHealthReport:
        report = CacheHealthReport()
        for check in (
            self._check_experimental_mcp_flag,
            self._check_model_not_in_env,
            self._check_claude_md_size,
            self._check_always_keep_config,
        ):
            risk = check(root)
            if risk:
                report.risks.append(risk)
        return report

    # ------------------------------------------------------------------ checks

    def _check_experimental_mcp_flag(self, root: Path) -> CacheRisk | None:
        if os.environ.get("ENABLE_EXPERIMENTAL_MCP_CLI", "").lower() in ("1", "true"):
            return None  # flag is set — MCP schemas load on-demand

        # Count MCP servers in Claude Code config
        mcp_count = self._count_mcp_servers(root)
        if mcp_count == 0:
            return None

        wasted = mcp_count * self.TOKENS_PER_MCP_SERVER
        return CacheRisk(
            severity="critical",
            code="missing_experimental_mcp_flag",
            message=(
                f"ENABLE_EXPERIMENTAL_MCP_CLI is not set. "
                f"{mcp_count} MCP server schema(s) load upfront "
                f"(~{wasted:,} tokens before you type a word)."
            ),
            fix=(
                "Add to your shell profile:\n"
                "  export ENABLE_EXPERIMENTAL_MCP_CLI=true\n"
                "Or prefix the session:\n"
                "  ENABLE_EXPERIMENTAL_MCP_CLI=true ce run 'your task'"
            ),
        )

    def _check_model_not_in_env(self, root: Path) -> CacheRisk | None:
        """Warn if ANTHROPIC_MODEL is set — it can cause implicit mid-session routing."""
        model_env = os.environ.get("ANTHROPIC_MODEL", "")
        if not model_env:
            return None
        return CacheRisk(
            severity="warning",
            code="model_env_override",
            message=(
                f"ANTHROPIC_MODEL={model_env!r} is set in the environment. "
                "ce's model router will be bypassed — model stays fixed at session start."
            ),
            fix="This is fine as long as you intended this model for the full session.",
        )

    def _check_claude_md_size(self, root: Path) -> CacheRisk | None:
        claude_md = root / "CLAUDE.md"
        if not claude_md.exists():
            return CacheRisk(
                severity="warning",
                code="missing_claude_md",
                message="No CLAUDE.md found. Claude will navigate files at token cost.",
                fix="Run `ce init` to generate CLAUDE.md.",
            )
        size = len(claude_md.read_bytes())
        if size > 4_000:
            return CacheRisk(
                severity="warning",
                code="claude_md_too_large",
                message=(
                    f"CLAUDE.md is {size:,} bytes. Files over ~4KB degrade "
                    "instruction-following — Claude starts ignoring later rules."
                ),
                fix=(
                    "Run `ce init --reimport` to split into root + @import subdirectory files. "
                    "Target: root under 2KB, subdirs under 600 bytes each."
                ),
            )
        return None

    def _check_always_keep_config(self, root: Path) -> CacheRisk | None:
        config_file = root / ".claude-efficient.toml"
        if not config_file.exists():
            return None
        try:
            import tomllib
            with open(config_file, "rb") as f:
                data = tomllib.load(f)
            always_keep = set(data.get("mcp", {}).get("always_keep", []))
            missing = {"claude_mem", "memory"} - always_keep
            if missing:
                return CacheRisk(
                    severity="critical",
                    code="claude_mem_not_protected",
                    message=(
                        f"{missing} are not in always_keep. "
                        "If auto_prune runs, claude-mem hooks will be disabled — "
                        "that session produces zero memory."
                    ),
                    fix=(
                        'Add to .claude-efficient.toml:\n'
                        '[mcp]\nalways_keep = ["claude_mem", "memory", "filesystem"]'
                    ),
                )
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------ helpers

    def _count_mcp_servers(self, root: Path) -> int:
        """
        Count MCP servers from Claude Code's config.
        Checks project .mcp.json first, then falls back to global config.
        """
        # Project-level override
        project_mcp = root / ".mcp.json"
        if project_mcp.exists():
            try:
                import json
                data = json.loads(project_mcp.read_text())
                return len(data.get("mcpServers", {}))
            except Exception:
                pass

        # Global Claude Code config
        global_config = Path.home() / ".claude" / "claude_desktop_config.json"
        if global_config.exists():
            try:
                import json
                data = json.loads(global_config.read_text())
                return len(data.get("mcpServers", {}))
            except Exception:
                pass

        return 0
```

## Tests

```python
# tests/test_cache_health.py
import os
from pathlib import Path
from unittest.mock import patch
from claude_efficient.analysis.cache_health import CacheHealthMonitor


def test_missing_experimental_flag_with_mcp_servers(tmp_path):
    monitor = CacheHealthMonitor()
    with patch.object(monitor, "_count_mcp_servers", return_value=8):
        with patch.dict(os.environ, {}, clear=True):
            report = monitor.check_all(tmp_path)
    codes = [r.code for r in report.risks]
    assert "missing_experimental_mcp_flag" in codes


def test_flag_set_no_mcp_risk(tmp_path):
    monitor = CacheHealthMonitor()
    with patch.object(monitor, "_count_mcp_servers", return_value=8):
        with patch.dict(os.environ, {"ENABLE_EXPERIMENTAL_MCP_CLI": "true"}):
            report = monitor.check_all(tmp_path)
    codes = [r.code for r in report.risks]
    assert "missing_experimental_mcp_flag" not in codes


def test_missing_claude_md_warns(tmp_path):
    report = CacheHealthMonitor().check_all(tmp_path)
    assert any(r.code == "missing_claude_md" for r in report.risks)


def test_oversized_claude_md_warns(tmp_path):
    (tmp_path / "CLAUDE.md").write_bytes(b"x" * 5_000)
    report = CacheHealthMonitor().check_all(tmp_path)
    assert any(r.code == "claude_md_too_large" for r in report.risks)


def test_healthy_session_no_risks(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# test\n")
    monitor = CacheHealthMonitor()
    with patch.object(monitor, "_count_mcp_servers", return_value=0):
        with patch.dict(os.environ, {"ENABLE_EXPERIMENTAL_MCP_CLI": "true"}):
            report = monitor.check_all(tmp_path)
    assert report.is_healthy
```

## Verification

```bash
pytest tests/test_cache_health.py -x
```

## Done → `/clear`

---
---

# SPEC_06 — `cli/init.py` (revised)
**Session goal:** Full `ce init` — backends, CLAUDE.md + @import tree, .claudeignore, PreCompact hook, claude-mem health check.
**Model:** Sonnet. **Est. context:** Small. **Clear after:** yes.
**Reads:** `CLAUDE.md`, method signatures from SPEC_02–05 and SPEC_01-04-FIXES only.

---

## Removes
- TASKS.md generation (claude-mem SessionEnd hook handles cross-session state)
- `ce update-tasks` command (PostToolUse hook handles task tracking)

## Adds
- claude-mem health check with helpful error if not running
- @import tree generation for qualifying subdirectories
- `.claude/settings.json` PreCompact hook
- Cache health pre-flight check

---

## Full implementation

```python
# src/claude_efficient/cli/init.py
from __future__ import annotations

import shutil
import subprocess
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
```

## Integration test

```python
# tests/test_init_command.py
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from claude_efficient.cli.init import init


def test_init_creates_core_files(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'")

    mock_backend = MagicMock()
    mock_backend.name = "gemini"
    mock_backend._build_payload.return_value = ""
    mock_backend.summarize.return_value = "# Test\n## Output format\nCode only."

    runner = CliRunner()
    with patch("claude_efficient.cli.init.detect_backend", return_value=mock_backend), \
         patch("claude_efficient.cli.init._check_claude_mem"):
        result = runner.invoke(init, ["--root", str(tmp_path), "--no-import-tree"])

    assert result.exit_code == 0
    assert (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / ".claudeignore").exists()
    assert (tmp_path / ".claude" / "settings.json").exists()
    # TASKS.md should NOT be created — claude-mem handles this
    assert not (tmp_path / "TASKS.md").exists()


def test_init_does_not_overwrite_precompact_hooks(tmp_path):
    """Existing .claude/settings.json hooks should be preserved."""
    import json
    (tmp_path / ".claude").mkdir()
    existing = {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "echo hi"}]}]}}
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps(existing))
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'")

    mock_backend = MagicMock()
    mock_backend.name = "gemini"
    mock_backend._build_payload.return_value = ""
    mock_backend.summarize.return_value = "# Test"

    runner = CliRunner()
    with patch("claude_efficient.cli.init.detect_backend", return_value=mock_backend), \
         patch("claude_efficient.cli.init._check_claude_mem"):
        result = runner.invoke(init, ["--root", str(tmp_path), "--no-import-tree"])

    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert "UserPromptSubmit" in settings["hooks"]   # original hook preserved
    assert "PreCompact" in settings["hooks"]          # new hook added
```

## Verification

```bash
pytest tests/test_init_command.py -x
ce init --root /tmp/test-project
```

## Done → `/clear`
