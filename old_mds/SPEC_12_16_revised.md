# SPEC_12 — `analysis/waste_detector.py`
**Session goal:** Seven audit detectors — original 6 plus cache invalidation detector.
**Model:** Sonnet. **Est. context:** Small. **Clear after:** yes.
**Reads:** `CLAUDE.md` only.

---

## Changes from original spec
- Added detector: `detect_cache_invalidation` — finds mid-session model switches and
  MCP server removal patterns that silently destroy prompt caching
- Compact detector: now flags 60%+ threshold (looking for the old bad threshold in configs)
- Updated: `detect_no_compact` threshold is now 45 turns (not 20)

---

## Full implementation

```python
# src/claude_efficient/analysis/waste_detector.py
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Finding:
    category: str
    severity: str          # "low" | "medium" | "high" | "critical"
    tokens_wasted: int
    fix: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class WasteReport:
    findings: list[Finding]
    total_tokens: int
    waste_tokens: int

    @property
    def waste_pct(self) -> float:
        return self.waste_tokens / self.total_tokens if self.total_tokens else 0.0


class WasteDetector:

    def detect_file_reads(self, transcript: str) -> Finding | None:
        reads = len(re.findall(r"(Read \d+ file|let me (check|look at|read))", transcript, re.I))
        if reads < 3:
            return None
        return Finding(
            "unnecessary_file_reads", "high", reads * 600,
            "Add codebase map to CLAUDE.md — Claude won't need to navigate.",
            [f"{reads} file-read operations detected"],
        )

    def detect_bash_retries(self, transcript: str) -> Finding | None:
        retries = len(re.findall(
            r"(ModuleNotFoundError|No module named|Exit code 1.*retry)", transcript
        ))
        if retries < 2:
            return None
        return Finding(
            "bash_retry_loops", "medium", retries * 400,
            "Add run/test commands to CLAUDE.md.",
            [f"{retries} failed bash attempts"],
        )

    def detect_large_pastes(self, transcript: str) -> Finding | None:
        user_turns = re.findall(
            r'"role":\s*"user"[^}]*"content":\s*"([^"]{1500,})"', transcript
        )
        if not user_turns:
            return None
        total = sum(len(t) for t in user_turns)
        return Finding(
            "large_user_pastes", "critical", total // 4,
            "Move spec content to CLAUDE.md. Use #filename refs instead of pasting.",
            [f"{len(user_turns)} large paste(s) detected"],
        )

    def detect_opus_overuse(self, transcript: str) -> Finding | None:
        if "claude-opus" not in transcript:
            return None
        if "claude-sonnet" in transcript:
            return None   # hybrid session — check for mid-session switch separately
        turns = transcript.count('"role": "assistant"')
        return Finding(
            "opus_overuse", "high", turns * 800,
            "Switch to Sonnet for implementation: ce run uses Sonnet by default.",
            ["Entire session on Opus — Sonnet handles implementation equally well"],
        )

    def detect_no_compact(self, transcript: str) -> Finding | None:
        if "/compact" in transcript:
            return None
        turns = transcript.count('"role":')
        if turns < 45:     # was 20 — long sessions are the real problem
            return None
        return Finding(
            "no_compact_usage", "medium", turns * 120,
            "Use /clear + fresh session at natural breakpoints. "
            "ce run monitors context at 45% threshold.",
            [f"{turns} turns with no /compact or /clear"],
        )

    def detect_narration(self, transcript: str) -> Finding | None:
        phrases = [
            "let me first check", "now i will", "i'll start by",
            "let me look at", "first, let me", "i need to check",
        ]
        count = sum(transcript.lower().count(p) for p in phrases)
        if count < 3:
            return None
        return Finding(
            "claude_narration", "low", count * 80,
            'Add to CLAUDE.md: "Code only. No narration before or between edits."',
            [f"{count} narration phrases found"],
        )

    def detect_cache_invalidation(self, transcript: str) -> Finding | None:
        """
        Detects patterns that silently destroy prompt cache value:
        1. Mid-session model switch (Opus → Sonnet or vice versa)
        2. Signs of MCP server toggling mid-session
        """
        evidence: list[str] = []
        tokens_lost = 0

        # Mid-session model switch
        models_found = re.findall(r"claude-(opus|sonnet|haiku)-[\d.-]+", transcript)
        if len(set(models_found)) > 1:
            evidence.append(
                f"Multiple models detected in session: {set(models_found)}. "
                "Each model switch invalidates the entire prompt cache prefix."
            )
            turns = transcript.count('"role":')
            tokens_lost += turns * 400   # rough: re-caching cost per remaining turn

        # Old compact threshold in config (60% instead of 45%)
        if re.search(r"threshold_pct\s*=\s*[6-9]\d", transcript):
            evidence.append(
                "Compact threshold >60% detected in config — "
                "context quality is already degraded by the time it fires."
            )

        if not evidence:
            return None

        return Finding(
            "cache_invalidation", "critical", tokens_lost,
            "Keep entire session on one model (model_router sets it once at start). "
            "Never switch models mid-session. Set threshold_pct = 45 in defaults.toml.",
            evidence,
        )

    def run(self, transcript_path: Path) -> WasteReport:
        text = transcript_path.read_text(errors="replace")
        findings: list[Finding] = []

        for detect in [
            self.detect_cache_invalidation,   # most severe — check first
            self.detect_large_pastes,
            self.detect_opus_overuse,
            self.detect_file_reads,
            self.detect_bash_retries,
            self.detect_no_compact,
            self.detect_narration,
        ]:
            f = detect(text)
            if f:
                findings.append(f)

        findings.sort(key=lambda f: f.tokens_wasted, reverse=True)
        total = text.count('"role":') * 1_500   # rough estimate
        waste = sum(f.tokens_wasted for f in findings)
        return WasteReport(findings, total, waste)
```

## Done → `/clear`

---
---

# SPEC_13 — `cli/audit.py` — `ce audit` command
**Session goal:** Report formatter + Click command wrapping WasteDetector.
**Model:** Sonnet. **Est. context:** Tiny. **Clear after:** yes.
**Reads:** `CLAUDE.md`, WasteDetector class signature only.

---

## Full implementation

```python
# src/claude_efficient/cli/audit.py
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
```

## Done → `/clear`

---
---

# SPEC_14 — `session/subagent_planner.py`
**Session goal:** Dependency graph + wave-based parallel subagent execution.
**Model:** Sonnet. **Est. context:** Medium. **Clear after:** yes.
**Reads:** `CLAUDE.md` only.

---

## Changes from original spec
- Each subagent call explicitly includes the model flag (chosen at plan time, not mid-run)
- Subagent prompt includes instruction to NOT switch models

---

## Full implementation

```python
# src/claude_efficient/session/subagent_planner.py
from __future__ import annotations

import concurrent.futures
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FileTask:
    target_file: str
    interface: str = ""
    depends_on: list[str] = field(default_factory=list)


@dataclass
class SubagentResult:
    file: str
    success: bool
    summary: str


def extract_file_targets(task_prompt: str) -> list[str]:
    """Extract file paths mentioned in a task prompt."""
    patterns = [
        r"(src/[\w/]+\.py)",
        r"([\w/]+/[\w]+\.py)",
        r"Build ([\w/\.]+)",
        r"Create ([\w/\.]+)",
    ]
    files: list[str] = []
    for p in patterns:
        files.extend(re.findall(p, task_prompt))
    return list(dict.fromkeys(files))   # dedup, preserve order


class SubagentPlanner:
    MAX_PARALLEL = 4

    def should_parallelize(self, task_prompt: str) -> bool:
        return len(extract_file_targets(task_prompt)) >= 2

    def build_waves(self, tasks: list[FileTask]) -> list[list[FileTask]]:
        """Topological sort into dependency waves."""
        waves: list[list[FileTask]] = []
        remaining = list(tasks)
        built: set[str] = set()

        while remaining:
            wave = [t for t in remaining if all(d in built for d in t.depends_on)]
            if not wave:
                wave = [remaining[0]]   # break cycle conservatively
            waves.append(wave)
            built.update(t.target_file for t in wave)
            remaining = [t for t in remaining if t not in wave]

        return waves

    def execute_wave(
        self,
        wave: list[FileTask],
        model: str = "claude-sonnet-4-6",
    ) -> list[SubagentResult]:
        """
        Execute a wave of independent tasks in parallel.
        model is fixed for all subagents — never switches mid-wave.
        """
        def run_task(task: FileTask) -> SubagentResult:
            interface_note = f"Interface contract: {task.interface}. " if task.interface else ""
            prompt = (
                f"Build {task.target_file}. "
                f"{interface_note}"
                f"See CLAUDE.md for project structure. "
                f"Output: file content only, no explanation, no preamble."
            )
            result = subprocess.run(
                ["claude", "--model", model, "-p", prompt],
                capture_output=True,
                text=True,
                timeout=300,
            )
            return SubagentResult(
                file=task.target_file,
                success=result.returncode == 0,
                summary=result.stdout[:500],
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.MAX_PARALLEL) as ex:
            return list(ex.map(run_task, wave))
```

## Tests
3 independent files → 1 wave of 3. File C depends on A → wave [A], then wave [C].

## Done → `/clear`

---
---

# SPEC_15 — `cli/commands.py` — `ce mem-search`, `ce scope-check`, `ce status`
**Session goal:** Three utility commands. Register all in cli/main.py.
**Model:** Sonnet. **Est. context:** Small. **Clear after:** yes.
**Reads:** `CLAUDE.md` only.

---

## Removes from original spec
- `ce update-tasks` — PostToolUse hook handles this automatically
- `TASKS.md`-based status — replaced by claude-mem timeline

## Adds
- `ce mem-search` — inspect what claude-mem has before starting a session
- `ce scope-check` — estimate token requirements for a task before running
- `ce status` — updated to show cache health + claude-mem status instead of TASKS.md

---

## Full implementation

```python
# src/claude_efficient/cli/commands.py
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
```

## Registration — add to `cli/main.py`

```python
# Append to src/claude_efficient/cli/main.py, after existing command imports

from claude_efficient.cli.commands import mem_search, scope_check, status

cli.add_command(mem_search)
cli.add_command(scope_check)
cli.add_command(status)
```

## Verification

```bash
ce mem-search "os_hook implementation"   # shows prior sessions or "not found"
ce scope-check "Build auth.py and user.py and session.py and refresh.py"
ce status
```

## Done → `/clear`

---
---

# SPEC_16 — PyPI Packaging + README
**Session goal:** Installable package, README, GitHub Actions CI.
**Model:** Sonnet. **Est. context:** Small. **Clear after:** yes.
**Reads:** `CLAUDE.md`, `pyproject.toml` only.

---

## Subtask 16.1 — Finalize `pyproject.toml`

Add `requests` to dependencies (needed by mcp_config, cache_health, session).
Add classifiers, URLs, license field. Confirm entry point works.

```toml
# Add to [project] in pyproject.toml
dependencies = [
    "click>=8.1",
    "requests>=2.31",
    "rich>=13.0",
    "tomllib>=1.0; python_version < '3.11'",
]

[project.urls]
Homepage = "https://github.com/YOUR_USERNAME/claude-efficient"
Issues   = "https://github.com/YOUR_USERNAME/claude-efficient/issues"

[project.scripts]
ce = "claude_efficient.cli.main:cli"
```

## Subtask 16.2 — README.md

```markdown
# claude-efficient

> Stop burning Claude Code tokens. `ce` wraps every session with automatic optimizations.

## Install
pip install claude-efficient

## Requires
- [claude-mem](https://github.com/thedotmack/claude-mem) for cross-session memory
- Gemini CLI (free) or Ollama (local) for zero-cost init analysis

## Setup (once per project)
ce init
# Generates CLAUDE.md + @import tree, .claudeignore, PreCompact hook
# Checks cache health, claude-mem status, ENABLE_EXPERIMENTAL_MCP_CLI

## Use
ce run "Build src/auth.py — JWT validation middleware"
# Auto-routes to Sonnet, checks cache health, injects claude-mem session brief,
# advises on MCP overhead, estimates scope

## Audit past sessions
ce audit session.log
# Detects: cache invalidation, large pastes, Opus overuse, bash retries, narration

## Other commands
ce mem-search "os_hook implementation"   # inspect prior session context
ce scope-check "Build X and Y and Z"    # estimate tokens before committing
ce status                                # project health dashboard

## What it fixes
| Issue | Fix | Savings |
|---|---|---|
| CLAUDE.md bloat | @import tree, 2KB root limit | ~45% |
| MCP schema overhead | ENABLE_EXPERIMENTAL_MCP_CLI advisory | ~40-105k tokens/session |
| Model switching | Session-start-only routing | cache preserved |
| Compaction loss | PreCompact hook + 45% threshold | ~60-70% per compact |
| Cold starts | claude-mem session brief | replaces TASKS.md paste |
```

## Subtask 16.3 — GitHub Actions CI

```yaml
# .github/workflows/ci.yml
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.11"}
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: pytest tests/ -x
```

## Subtask 16.4 — Build + test install

```bash
pip install build
python -m build
pip install dist/claude_efficient-0.1.0-py3-none-any.whl
ce --help
ce status
```

## Done → project complete.
