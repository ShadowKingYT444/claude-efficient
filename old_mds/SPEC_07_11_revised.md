# SPEC_07 — `session/model_router.py`
**Session goal:** Session-start-only model selection. Never switches mid-session.
**Model:** Sonnet. **Est. context:** Tiny. **Clear after:** yes.
**Reads:** `CLAUDE.md` only.

---

## Architecture note

The original spec's "hybrid session" pattern (Opus for planning → Sonnet per step)
would blow up the cache on the Opus-to-Sonnet transition. The correct pattern:
- Opus for architectural/planning sessions — the WHOLE session stays on Opus
- Sonnet for implementation sessions — the WHOLE session stays on Sonnet
- Model is chosen ONCE, injected into the claude command, then locked for the session

---

## Full implementation

```python
# src/claude_efficient/session/model_router.py
from __future__ import annotations

from dataclasses import dataclass

SONNET = "claude-sonnet-4-6"
OPUS = "claude-opus-4-6"

# Triggers indicating this session needs architectural reasoning on Opus.
# If ANY trigger matches → entire session uses Opus.
OPUS_TRIGGERS: frozenset[str] = frozenset({
    "architect",
    "design system",
    "design the",
    "write claude.md",
    "write gemini.md",
    "how should we structure",
    "explain the tradeoffs",
    "refactor entire",
    "debug this system",
    "master plan",
    "system design",
})


@dataclass(frozen=True)
class RoutingDecision:
    model: str
    reason: str
    note: str = ""


def route(task_prompt: str) -> RoutingDecision:
    """
    Select model for the FULL session. This decision is made once, at session start.
    The chosen model must not change mid-session — doing so invalidates the prompt cache.
    """
    lowered = task_prompt.lower()
    for trigger in OPUS_TRIGGERS:
        if trigger in lowered:
            return RoutingDecision(
                model=OPUS,
                reason=f"planning keyword: '{trigger}'",
                note="Full session on Opus — do not switch to Sonnet mid-session",
            )
    return RoutingDecision(
        model=SONNET,
        reason="implementation task — Sonnet default",
        note="Sonnet saves on output tokens; Opus savings disappear with cache hits",
    )


def inject_model_flag(claude_args: list[str], model: str) -> list[str]:
    """Prepend --model flag only if not already present."""
    if "--model" not in claude_args:
        return ["--model", model] + claude_args
    return claude_args
```

## Tests

```python
# tests/test_model_router.py
from claude_efficient.session.model_router import route, SONNET, OPUS

def test_implementation_routes_to_sonnet():
    assert route("Build collectors/os_hook.py").model == SONNET

def test_architecture_routes_to_opus():
    assert route("architect the entire data pipeline").model == OPUS

def test_empty_prompt_defaults_to_sonnet():
    assert route("").model == SONNET

def test_planning_keyword_routes_to_opus():
    assert route("design the authentication system").model == OPUS

def test_route_is_stable_same_input():
    """Same prompt must always produce same model — routing must be deterministic."""
    assert route("Build auth.py") == route("Build auth.py")
```

## Done → `/clear`

---
---

# SPEC_08 — `session/compact_manager.py`
**Session goal:** Compact threshold at 45%, prefer /clear, session scope analyzer.
**Model:** Sonnet. **Est. context:** Tiny. **Clear after:** yes.
**Reads:** `CLAUDE.md` only.

---

## Architecture changes from original spec

- Threshold: 45% (was 60%). Context quality degrades non-linearly; at 60% Claude is
  already missing things.
- Default action: recommend /clear + fresh session when possible. /compact is for when
  you have state you genuinely cannot reconstruct. Two compactions per session = task
  was scoped too large.
- Added: SessionScopeAnalyzer estimates token requirement before starting and warns
  if the task will likely require >1 compact.

---

## Full implementation

```python
# src/claude_efficient/session/compact_manager.py
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class CompactAction(Enum):
    NONE = "none"
    WARN = "warn"
    SUGGEST_CLEAR = "suggest_clear"    # preferred: fresh session
    COMPACT_NOW = "compact_now"        # fallback when state must be preserved
    DANGER = "danger"                  # past 70% — compact immediately regardless


@dataclass
class CompactState:
    action: CompactAction
    message: str
    compact_instruction: str | None = None


# Injected into /compact to preserve maximum useful context.
COMPACT_INSTRUCTION = (
    "/compact Focus on: file states written this session, interfaces defined, "
    "what was verified passing. Discard: file read contents, bash error retries, "
    "narration, failed approaches."
)

BREAKPOINT_SIGNALS = {"done", "complete", "created", "written", "verified", "passing"}
MID_WRITE_SIGNALS = {"writing", "building", "implementing", "creating", "generating"}


class CompactManager:
    COMPACT_THRESHOLD = 0.45    # was 0.60 — act before quality degrades
    DANGER_THRESHOLD = 0.70     # was 0.80

    def check(self, used_pct: float, current_task: str = "") -> CompactState:
        task_lower = current_task.lower()

        if used_pct < self.COMPACT_THRESHOLD:
            return CompactState(CompactAction.NONE, f"{used_pct:.0%} — healthy")

        if used_pct >= self.DANGER_THRESHOLD:
            return CompactState(
                CompactAction.DANGER,
                f"⚠ {used_pct:.0%} — past danger threshold. /compact immediately.",
                COMPACT_INSTRUCTION,
            )

        if any(s in task_lower for s in MID_WRITE_SIGNALS):
            return CompactState(
                CompactAction.WARN,
                f"{used_pct:.0%} — mid-write. Finish current file, then act.",
            )

        if any(s in task_lower for s in BREAKPOINT_SIGNALS):
            return CompactState(
                CompactAction.SUGGEST_CLEAR,
                (
                    f"{used_pct:.0%} — natural breakpoint. "
                    "Prefer: /clear + start fresh session (no information loss). "
                    "Use /compact only if session state is hard to reconstruct."
                ),
                COMPACT_INSTRUCTION,
            )

        return CompactState(
            CompactAction.SUGGEST_CLEAR,
            (
                f"{used_pct:.0%} — approaching limit. "
                "Recommended: finish current task, then /clear + new session."
            ),
        )


# ── Session scope analyzer ───────────────────────────────────────────────────

@dataclass
class ScopeEstimate:
    estimated_tokens: int
    will_require_compact: bool
    warning: str | None
    recommendation: str


class SessionScopeAnalyzer:
    """
    Estimates token requirement for a task before starting.
    Warns if the task will likely need >1 compact cycle.
    """

    # Rough token cost heuristics per operation type
    TOKENS_PER_FILE_WRITE = 3_000
    TOKENS_PER_FILE_READ = 1_500
    SESSION_OVERHEAD = 8_000     # CLAUDE.md + MCP stubs + system prompt
    SAFE_WINDOW = 120_000        # conservative estimate of usable context

    def estimate(self, task_prompt: str, root: Path = Path(".")) -> ScopeEstimate:
        files_mentioned = self._count_file_references(task_prompt)
        has_multi_task = self._is_multi_task(task_prompt)

        estimated = (
            self.SESSION_OVERHEAD
            + files_mentioned * self.TOKENS_PER_FILE_WRITE
            + files_mentioned * self.TOKENS_PER_FILE_READ
        )

        will_compact = estimated > self.SAFE_WINDOW * 0.45

        warning = None
        recommendation = "Task fits in one session — proceed."

        if has_multi_task and files_mentioned > 5:
            warning = (
                f"This prompt references ~{files_mentioned} files and appears multi-task. "
                f"Estimated {estimated:,} tokens — likely needs >1 compact cycle."
            )
            recommendation = (
                "Split into separate `ce run` calls, one file or concern per call. "
                "Use CLAUDE.md @imports for shared context."
            )
        elif will_compact:
            warning = f"Estimated {estimated:,} tokens — may hit 45% threshold mid-session."
            recommendation = "Consider breaking into two focused sessions."

        return ScopeEstimate(
            estimated_tokens=estimated,
            will_require_compact=will_compact,
            warning=warning,
            recommendation=recommendation,
        )

    def _count_file_references(self, prompt: str) -> int:
        patterns = [r"[\w/]+\.py", r"[\w/]+\.ts", r"[\w/]+\.js", r"[\w/]+\.go"]
        files: set[str] = set()
        for p in patterns:
            files.update(re.findall(p, prompt))
        return max(len(files), 1)

    def _is_multi_task(self, prompt: str) -> bool:
        return (
            prompt.count(" and ") > 2
            or prompt.count(",") > 4
            or "\n-" in prompt
        )
```

## Tests

```python
# tests/test_compact_manager.py
from claude_efficient.session.compact_manager import CompactManager, CompactAction, SessionScopeAnalyzer

def test_healthy_below_threshold():
    assert CompactManager().check(0.30).action == CompactAction.NONE

def test_suggests_clear_at_threshold():
    state = CompactManager().check(0.50, "task complete")
    assert state.action == CompactAction.SUGGEST_CLEAR

def test_danger_threshold():
    assert CompactManager().check(0.75).action == CompactAction.DANGER

def test_mid_write_warns_not_clears():
    state = CompactManager().check(0.50, "building the module")
    assert state.action == CompactAction.WARN

def test_scope_analyzer_warns_large_task():
    analyzer = SessionScopeAnalyzer()
    est = analyzer.estimate(
        "Build auth.py, user.py, session.py, middleware.py, "
        "tokens.py, refresh.py and also update tests for all of them"
    )
    assert est.warning is not None
```

## Done → `/clear`

---
---

# SPEC_09 — `session/mcp_config.py`
**Session goal:** MCP overhead advisor. Replaces the pruner concept entirely.
**Model:** Sonnet. **Est. context:** Tiny. **Clear after:** yes.
**Reads:** `CLAUDE.md` only.

---

## Architecture

The original MCPPruner was architecturally wrong in two ways:
1. Removing servers mid-session invalidates prompt cache prefix
2. Removing claude_mem destroys the capture pipeline silently

The correct solution has two layers:
1. **ENABLE_EXPERIMENTAL_MCP_CLI=true** — native deferred loading. MCP tool schemas
   load on-demand instead of upfront. Reclaims 40-105k tokens at session start. This
   renders the pruner concept obsolete.
2. **Session-start config** — if deferral isn't available, generate a per-session
   `.mcp.json` that excludes irrelevant servers BEFORE the session starts (so the
   cache prefix is established correctly from turn 1).

The `mcp_pruner.py` file already exists; this spec adds `mcp_config.py` alongside it
and disables auto_prune in defaults.

---

## Full implementation

```python
# src/claude_efficient/session/mcp_config.py
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ALWAYS_KEEP: frozenset[str] = frozenset({"claude_mem", "memory", "filesystem"})

# Keywords that indicate a server is relevant to a task
MCP_RELEVANCE_MAP: dict[str, list[str]] = {
    "gmail": ["email", "draft", "reply", "inbox", "send", "mail"],
    "google_calendar": ["calendar", "meeting", "schedule", "event", "appointment"],
    "google_drive": ["document", "drive", "gdoc", "sheet", "slides"],
    "github": ["pr", "pull request", "commit", "issue", "repo", "branch", "git"],
    "slack": ["slack", "channel", "dm", "message"],
    "asana": ["task", "asana", "sprint", "ticket", "project management"],
}


@dataclass
class McpSessionPlan:
    has_experimental_flag: bool
    active_servers: list[str]
    deferred_servers: list[str]
    tokens_overhead: int
    advice: list[str] = field(default_factory=list)


class McpConfigAdvisor:
    """
    Advises on MCP configuration for a session.
    Never removes servers mid-session. Only recommends or generates pre-session config.
    """

    TOKENS_PER_SERVER = 1_200

    def plan_session(
        self,
        task_prompt: str,
        all_servers: list[str],
        root: Path = Path("."),
    ) -> McpSessionPlan:
        has_flag = os.environ.get("ENABLE_EXPERIMENTAL_MCP_CLI", "").lower() in ("1", "true")
        always_keep = self._load_always_keep(root)
        lowered = task_prompt.lower()

        if has_flag:
            # With deferred loading, all servers are "active" but schemas load on demand.
            # No overhead concern — report everything as active.
            return McpSessionPlan(
                has_experimental_flag=True,
                active_servers=all_servers,
                deferred_servers=[],
                tokens_overhead=0,
                advice=[
                    "ENABLE_EXPERIMENTAL_MCP_CLI=true detected — schemas load on demand.",
                    "No MCP token overhead at session start.",
                ],
            )

        # Without the flag: identify which servers are actually needed
        active, deferred = [], []
        for server in all_servers:
            if server in always_keep:
                active.append(server)
                continue
            keywords = MCP_RELEVANCE_MAP.get(server, [])
            if any(kw in lowered for kw in keywords):
                active.append(server)
            else:
                deferred.append(server)

        overhead = len(all_servers) * self.TOKENS_PER_SERVER  # current overhead
        savings = len(deferred) * self.TOKENS_PER_SERVER

        advice = []
        if deferred:
            advice.append(
                f"{len(deferred)} server(s) appear unused for this task "
                f"(~{savings:,} tokens): {deferred}"
            )
            advice.append(
                "To reduce overhead: set ENABLE_EXPERIMENTAL_MCP_CLI=true (preferred), "
                "or run `ce mcp-session-config` to generate a task-scoped .mcp.json "
                "BEFORE starting the session."
            )
        if not has_flag:
            advice.append(
                "Recommended: export ENABLE_EXPERIMENTAL_MCP_CLI=true in your shell profile."
            )

        return McpSessionPlan(
            has_experimental_flag=False,
            active_servers=active,
            deferred_servers=deferred,
            tokens_overhead=overhead,
            advice=advice,
        )

    def write_session_mcp_json(
        self,
        root: Path,
        active_servers: list[str],
        source_config: Path | None = None,
    ) -> Path:
        """
        Write a .mcp.json for the session that includes only active_servers.
        Must be called BEFORE the session starts — never during.
        Source config is read from ~/.claude/claude_desktop_config.json if not specified.
        """
        if source_config is None:
            source_config = Path.home() / ".claude" / "claude_desktop_config.json"

        all_server_defs: dict = {}
        if source_config.exists():
            try:
                data = json.loads(source_config.read_text())
                all_server_defs = data.get("mcpServers", {})
            except Exception:
                pass

        session_servers = {
            name: cfg
            for name, cfg in all_server_defs.items()
            if name in active_servers
        }

        out = root / ".mcp.json"
        out.write_text(json.dumps({"mcpServers": session_servers}, indent=2))
        return out

    def _load_always_keep(self, root: Path) -> frozenset[str]:
        for candidate in (
            root / ".claude-efficient.toml",
            Path(__file__).parent.parent / "config" / "defaults.toml",
        ):
            if candidate.exists():
                try:
                    import tomllib
                    with open(candidate, "rb") as f:
                        return frozenset(
                            tomllib.load(f).get("mcp", {}).get("always_keep", DEFAULT_ALWAYS_KEEP)
                        )
                except Exception:
                    pass
        return DEFAULT_ALWAYS_KEEP
```

## Tests

```python
# tests/test_mcp_config.py
import os
from pathlib import Path
from unittest.mock import patch
from claude_efficient.session.mcp_config import McpConfigAdvisor

def test_with_experimental_flag_no_overhead():
    advisor = McpConfigAdvisor()
    with patch.dict(os.environ, {"ENABLE_EXPERIMENTAL_MCP_CLI": "true"}):
        plan = advisor.plan_session("build auth.py", ["gmail", "claude_mem", "github"])
    assert plan.has_experimental_flag
    assert plan.tokens_overhead == 0
    assert plan.deferred_servers == []

def test_always_keep_never_deferred():
    advisor = McpConfigAdvisor()
    with patch.dict(os.environ, {}, clear=True):
        plan = advisor.plan_session("build auth.py", ["claude_mem", "gmail"])
    assert "claude_mem" in plan.active_servers
    assert "gmail" in plan.deferred_servers

def test_relevant_server_stays_active():
    advisor = McpConfigAdvisor()
    with patch.dict(os.environ, {}, clear=True):
        plan = advisor.plan_session("draft an email to the team", ["gmail", "github"])
    assert "gmail" in plan.active_servers
    assert "github" in plan.deferred_servers
```

## Done → `/clear`

---
---

# SPEC_10 — `prompt/optimizer.py`
**Session goal:** Filler stripping, anti-pattern detection, scope estimation hint.
**Model:** Sonnet. **Est. context:** Tiny. **Clear after:** yes.
**Reads:** `CLAUDE.md` only.

---

## Changes from original spec
- Added: multi-task scope warning now includes a concrete split suggestion
- Added: long prompt warning references @file refs (not just CLAUDE.md)
- Minor: paste-detection regex improved

---

## Full implementation

```python
# src/claude_efficient/prompt/optimizer.py
from __future__ import annotations

import re
from dataclasses import dataclass, field

FILLER_PATTERNS = [
    r"\bplease\s+",
    r"\bcan you\s+",
    r"\bi want you to\s+",
    r"\bi need you to\s+",
    r"\bmake sure to\s+",
    r"\bdon't forget to\s+",
    r"\bas we discussed[,\s]+",
    r"\bjust\s+",
    r"\bgo ahead and\s+",
    r"\bfeel free to\s+",
]

OUTPUT_FORMAT_HINT = "\nOutput: code only, no preamble."


@dataclass
class OptimizedPrompt:
    text: str
    warnings: list[str] = field(default_factory=list)
    chars_saved: int = 0


def optimize(prompt: str) -> OptimizedPrompt:
    warnings: list[str] = []
    original_len = len(prompt)

    # Strip filler phrases
    cleaned = prompt
    for pattern in FILLER_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"  +", " ", cleaned).strip()

    # Anti-pattern: vague prompt
    if len(cleaned.split()) < 6:
        warnings.append(
            "Vague prompt — add: target file, what to change, expected behavior."
        )

    # Anti-pattern: massive paste (likely spec content)
    if len(cleaned) > 1_500:
        warnings.append(
            "Long prompt (>1,500 chars). Move spec content to CLAUDE.md or "
            "use `#filename` to reference a file without pasting it."
        )

    # Anti-pattern: multi-task in one prompt
    if cleaned.count(" and ") > 2 or cleaned.count(",") > 4 or "\n-" in cleaned:
        warnings.append(
            "Multi-task prompt — split into separate `ce run` calls. "
            "Each call gets a clean context; combined calls pollute each other."
        )

    # Add output hint if not already present
    if "output:" not in cleaned.lower() and "code only" not in cleaned.lower():
        cleaned += OUTPUT_FORMAT_HINT

    return OptimizedPrompt(
        text=cleaned,
        warnings=warnings,
        chars_saved=original_len - len(cleaned),
    )
```

## Tests: filler stripped, short prompt warns, long prompt warns, hint appended when missing.

## Done → `/clear`

---
---

# SPEC_11 — `cli/session.py` — `ce run` command
**Session goal:** Wire all session components into `ce run` with claude-mem session brief.
**Model:** Sonnet. **Est. context:** Small. **Clear after:** yes.
**Reads:** `CLAUDE.md`, method signatures from SPEC_07–10 only.

---

## Key changes from original spec
- Cache health check before every session
- claude-mem session brief injected as context (replaces TASKS.md paste)
- McpConfigAdvisor replaces MCPPruner; prints advice, does not act
- Scope estimate warns before large tasks
- Model is injected ONCE, never changed

---

## Full implementation

```python
# src/claude_efficient/cli/session.py
from __future__ import annotations

import subprocess
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
    subprocess.run(cmd, cwd=root_path)


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
```

## Integration test

```bash
ce run "Build src/main.py — simple hello world" --dry-run
# Should print: cache health, model, scope estimate, MCP advice, dry run command
```

## Done → `/clear`
