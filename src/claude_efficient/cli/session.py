from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from contextlib import nullcontext
from functools import partial
from pathlib import Path

import click

from claude_efficient.analysis.cache_health import CacheHealthMonitor
from claude_efficient.config.defaults import HelperMode
from claude_efficient.config.loader import resolve_helpers_config
from claude_efficient.generators.backends import HelperTask
from claude_efficient.generators.mcp import classify_mcp_relevance
from claude_efficient.generators.orchestrator import invoke_helper
from claude_efficient.generators.prompt import normalize_prompt
from claude_efficient.prompt.optimizer import OptimizedPrompt, optimize
from claude_efficient.session.compact_manager import SessionScopeAnalyzer
from claude_efficient.session.mcp_config import McpConfigAdvisor
from claude_efficient.session.mcp_pruner import (
    auto_pruned_session_config,
    discover_enabled_servers,
    is_auto_prune_enabled,
    prune,
)
from claude_efficient.session.model_router import route
from claude_efficient.session.output_budget import estimate_output_budget, format_budget_hint


def _session_env() -> dict[str, str]:
    """Build subprocess env with caching optimizations auto-applied."""
    env = os.environ.copy()
    env.setdefault("ENABLE_EXPERIMENTAL_MCP_CLI", "true")
    return env


@click.command()
@click.argument("task", required=False)
@click.option("--root", default=".", type=click.Path())
@click.option("--model", default=None, help="Override auto model routing")
@click.option("--no-health-check", is_flag=True, help="Skip cache health pre-flight")
@click.option("--dry-run", is_flag=True, help="Show plan without executing")
@click.option(
    "-i",
    "--interactive",
    is_flag=True,
    help="Launch Claude Code in interactive mode (no task required).",
)
@click.option(
    "-p",
    "--pipe",
    is_flag=True,
    help="Single-turn pipe mode (no session cache). Default is interactive.",
)
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
def run(
    task: str | None,
    root: str,
    model: str | None,
    no_health_check: bool,
    dry_run: bool,
    interactive: bool,
    pipe: bool,
    helpers: str | None,
    helper_backend: str | None,
) -> None:
    """Optimized session wrapper for a Claude Code task."""
    root_path = Path(root).resolve()
    env = _session_env()
    sep = "-" * 50

    claude_md = root_path / "CLAUDE.md"
    if not claude_md.exists():
        click.secho(
            "[ce] WARNING: No CLAUDE.md found. Claude will waste tokens navigating.",
            fg="yellow",
        )
        click.secho("[ce] Fix: run `ce init` first to generate CLAUDE.md", fg="yellow")

    if pipe and interactive:
        raise click.UsageError("Choose only one mode: --pipe or --interactive.")

    task_text = (task or "").strip()
    has_task = bool(task_text)
    force_live_interactive = interactive and not has_task

    if pipe and not has_task:
        raise click.UsageError("TASK is required when using --pipe.")

    if not has_task and not interactive:
        raise click.UsageError("TASK is required unless --interactive is set.")

    if not no_health_check:
        report = CacheHealthMonitor().check_all(root_path)
        if env.get("ENABLE_EXPERIMENTAL_MCP_CLI", "").lower() in ("1", "true"):
            report.risks = [
                risk
                for risk in report.risks
                if risk.code != "missing_experimental_mcp_flag"
            ]
        for risk in report.risks:
            color = "red" if risk.severity == "critical" else "yellow"
            click.secho(f"[ce] [{risk.severity.upper()}] {risk.message}", fg=color)
            if risk.severity == "critical" and not dry_run:
                click.secho(f"[ce] Fix: {risk.fix}", fg=color)
                if not click.confirm("[ce] Continue anyway?", default=False):
                    raise SystemExit(0)

    mode, backend = resolve_helpers_config(helpers, helper_backend, root_path)

    def _helper(content: str, task_enum: HelperTask) -> str:
        return invoke_helper(task_enum, content, mode=mode, backend=backend).text

    invoke_fn = (
        None
        if mode is HelperMode.off
        else partial(_helper, task_enum=HelperTask.prompt_normalize)
    )

    normalized = normalize_prompt(task_text, invoke_helper_fn=invoke_fn) if has_task else ""

    opt = optimize(normalized)
    for warning in opt.warnings:
        click.secho(f"[ce] WARNING {warning}", fg="yellow")
    if opt.chars_saved > 0:
        click.echo(f"[ce] Prompt: -{opt.chars_saved} chars after optimization")

    if has_task:
        scope = SessionScopeAnalyzer().estimate(opt.text, root_path)
        if scope.warning:
            click.secho(f"[ce] WARNING Scope: {scope.warning}", fg="yellow")
            click.echo(f"[ce]   -> {scope.recommendation}")

        # Output budget: inject token budget hint based on task type
        try:
            est = int(scope.estimated_tokens)
            file_count = est // 4500 if est > 0 else 1
        except (TypeError, ValueError):
            file_count = 1
        budget = estimate_output_budget(opt.text, max(file_count, 1))
        budget_hint = format_budget_hint(budget)
        opt = OptimizedPrompt(
            text=opt.text + budget_hint,
            chars_saved=opt.chars_saved,
            warnings=opt.warnings,
        )
        click.echo(f"[ce] Output budget: ~{budget.estimated_tokens} tokens")

    routing_text = opt.text if opt.text else "Start interactive Claude Code session."
    decision = route(routing_text) if model is None else None
    chosen_model = model or decision.model
    reason = f" ({decision.reason})" if decision else " (manual override)"
    click.echo(f"[ce] Model: {chosen_model}{reason}")
    if decision and decision.note:
        click.echo(f"[ce]   {decision.note}")

    enabled_mcps: list[str] = []
    fast_path = env.get("ENABLE_EXPERIMENTAL_MCP_CLI", "").lower() in ("1", "true")
    mcp_session_ctx = nullcontext(None)

    if has_task:
        enabled_mcps = _read_enabled_mcps(root_path)
        mcp_invoke_fn = (
            None
            if mode is HelperMode.off
            else partial(_helper, task_enum=HelperTask.mcp_relevance_classify)
        )
        mcp_result = classify_mcp_relevance(
            normalized,
            enabled_mcps,
            invoke_helper_fn=mcp_invoke_fn,
            fast_path_enabled=fast_path,
        )
        if mcp_result.relevant:
            plan = McpConfigAdvisor().plan_session(opt.text, mcp_result.relevant, root_path)
            for advice in plan.advice:
                click.secho(f"[ce] MCP: {advice}", fg="cyan")
        if enabled_mcps and not fast_path:
            if dry_run:
                preview = prune(opt.text, enabled_mcps, root=root_path)
                if is_auto_prune_enabled(root_path) and preview.pruned:
                    click.secho(
                        "[ce] MCP auto-prune (dry-run): "
                        f"keep={preview.keep}, prune={preview.pruned}",
                        fg="cyan",
                    )
            else:
                mcp_session_ctx = auto_pruned_session_config(
                    opt.text,
                    enabled_mcps,
                    root=root_path,
                )

    brief = _fetch_mem_brief(opt.text, root=root_path) if has_task else None
    if brief:
        click.echo(f"[ce] Memory: {brief}")

    final_prompt = opt.text
    if brief:
        final_prompt = f"[Session context from prior work: {brief}]\n\n{opt.text}"

    if pipe:
        ctx_prompt = _build_pipe_context(final_prompt, root_path)
        if ctx_prompt is not final_prompt:
            click.echo(
                f"[ce] Pipe: +{len(ctx_prompt) - len(final_prompt)} chars context injected"
            )
        final_prompt = ctx_prompt
        cmd = ["claude", "--model", chosen_model, "-p", final_prompt]
    elif force_live_interactive:
        cmd = ["claude", "--model", chosen_model]
    else:
        cmd = ["claude", "--model", chosen_model, final_prompt]

    if dry_run:
        mode_label = "PIPE (single-turn)" if pipe else "INTERACTIVE (session cache enabled)"
        click.secho(f"\n{sep}", fg="cyan")
        click.secho(f"[ce] DRY RUN - mode: {mode_label}", fg="cyan")
        if pipe:
            click.echo(f"  claude --model {chosen_model} -p <optimized_prompt>")
            click.echo(f"  Prompt length: {len(final_prompt)} chars")
        elif force_live_interactive:
            click.echo(f"  claude --model {chosen_model}")
            click.echo("  Prompt length: 0 chars")
        else:
            click.echo(f"  claude --model {chosen_model} <optimized_prompt>")
            click.echo(f"  Prompt length: {len(final_prompt)} chars")
        click.echo(
            f"  MCP deferred loading: {env.get('ENABLE_EXPERIMENTAL_MCP_CLI', 'false')}"
        )
        return

    mode_label = "pipe" if pipe else "interactive"
    click.secho(f"\n[ce] Running on {chosen_model} ({mode_label})...\n", fg="cyan")

    with mcp_session_ctx as mcp_session:
        if mcp_session and mcp_session.auto_prune_enabled:
            if mcp_session.applied:
                click.secho(
                    "[ce] MCP auto-prune applied: "
                    f"active={mcp_session.active_servers}, "
                    f"pruned={mcp_session.result.pruned}",
                    fg="cyan",
                )
            elif mcp_session.reason:
                click.secho(f"[ce] MCP auto-prune skipped: {mcp_session.reason}", fg="yellow")

        if pipe:
            tel_cmd = cmd + ["--output-format", "json"]
            t0 = time.monotonic()
            proc = subprocess.run(
                tel_cmd,
                cwd=root_path,
                env=env,
                capture_output=True,
                text=True,
                shell=(sys.platform == "win32"),
            )
            duration = time.monotonic() - t0

            actual_input = actual_output = actual_cache = None
            text_result = proc.stdout
            try:
                data = json.loads(proc.stdout)
                text_result = data.get("result", proc.stdout)
                usage = data.get("usage", {})
                actual_input = usage.get("input_tokens")
                actual_output = usage.get("output_tokens")
                actual_cache = usage.get("cache_read_input_tokens")
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass
            if text_result:
                click.echo(text_result)

            _write_telemetry(
                root_path,
                task_text,
                opt,
                mode="pipe",
                model=chosen_model,
                actual_input=actual_input,
                actual_output=actual_output,
                actual_cache=actual_cache,
                duration=duration,
            )

        else:
            t0 = time.monotonic()
            subprocess.run(cmd, cwd=root_path, env=env, shell=(sys.platform == "win32"))
            duration = time.monotonic() - t0

            # Try to extract real token usage from Claude Code session data
            actual_input = actual_output = actual_cache = None
            try:
                from claude_efficient.analysis.session_parser import parse_last_session
                session_data = parse_last_session(root_path)
                if session_data and session_data.total_input > 0:
                    actual_input = session_data.total_input
                    actual_output = session_data.total_output
                    actual_cache = session_data.total_cache_read
                    click.echo(
                        f"[ce] Session: {session_data.turn_count} turns, "
                        f"{actual_input:,} input, {actual_output:,} output, "
                        f"{actual_cache:,} cached"
                    )
            except Exception:
                pass

            _write_telemetry(
                root_path,
                task_text,
                opt,
                mode="interactive",
                model=chosen_model,
                actual_input=actual_input,
                actual_output=actual_output,
                actual_cache=actual_cache,
                duration=duration,
            )

            # Post-session analysis: warn about long sessions
            if duration and duration > 600:
                click.secho(
                    "[ce] Long session detected. Consider splitting future tasks "
                    "and using /clear between logical units.",
                    fg="yellow",
                )


def _read_enabled_mcps(root: Path) -> list[str]:
    config_file = root / ".claude-efficient.toml"
    if not config_file.exists():
        return discover_enabled_servers(root)
    try:
        import tomllib

        with open(config_file, "rb") as f:
            configured = tomllib.load(f).get("mcp", {}).get("enabled_servers", [])
            if isinstance(configured, list) and configured:
                return [name for name in configured if isinstance(name, str)]
    except Exception:
        pass
    return discover_enabled_servers(root)


def _write_telemetry(
    root: Path,
    original_task: str,
    opt: OptimizedPrompt,
    *,
    mode: str,
    model: str,
    actual_input: int | None = None,
    actual_output: int | None = None,
    actual_cache: int | None = None,
    duration: float | None = None,
) -> None:
    from datetime import datetime
    from claude_efficient.analysis.telemetry import (
        TelemetryRecord,
        estimate_baseline_input_tokens,
        estimate_session_input_savings_pct,
        record as tel_record,
    )

    baseline_input = estimate_baseline_input_tokens(actual_input, actual_cache)
    savings_pct = estimate_session_input_savings_pct(actual_input, actual_cache)
    meets_50pct_target = savings_pct >= 50.0 if savings_pct is not None else None

    rec = TelemetryRecord(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        mode=mode,
        model=model,
        prompt_chars_original=len(original_task),
        prompt_chars_optimized=len(opt.text),
        chars_saved=opt.chars_saved,
        actual_input_tokens=actual_input,
        actual_output_tokens=actual_output,
        actual_cache_read_tokens=actual_cache,
        baseline_input_tokens=baseline_input,
        saved_input_tokens=actual_cache,
        session_input_savings_pct=savings_pct,
        meets_50pct_savings_target=meets_50pct_target,
        session_duration_s=round(duration, 2) if duration is not None else None,
    )
    tel_record(root, rec)
    click.secho("[ce] Telemetry saved -> .ce-telemetry.jsonl", fg="cyan")


def _normalize_mem_text(value: str) -> str:
    return " ".join(value.split())


def _build_mem_queries(task: str, root: Path | None = None) -> list[str]:
    import re

    task = task.strip()
    if not task:
        return []

    queries: list[str] = [task]
    files = re.findall(
        r"\b[\w./\\-]+\.(?:py|js|ts|tsx|jsx|go|rs|java|rb|toml|json|yaml|yml|sh|c|cpp|h)\b",
        task,
    )
    if files:
        queries.append(" ".join(files[:3]))

    if root is not None:
        repo_hint = f"{root.name} {task[:120]}".strip()
        if repo_hint and repo_hint not in queries:
            queries.append(repo_hint)

    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_/-]{3,}", task.lower())
    stop = {
        "this",
        "that",
        "with",
        "from",
        "into",
        "have",
        "make",
        "build",
        "update",
        "implement",
    }
    keywords = [word for word in words if word not in stop][:8]
    if keywords:
        kw_query = " ".join(keywords)
        if kw_query not in queries:
            queries.append(kw_query)

    return queries[:4]


def _fetch_mem_brief(task: str, max_chars: int = 320, root: Path | None = None) -> str | None:
    """
    Query claude-mem using multiple compact queries and return a merged brief.
    Keeps output short to avoid regressing token cost while improving recall.
    """
    queries = _build_mem_queries(task, root=root)
    if not queries:
        return None

    try:
        import requests

        ranked: list[tuple[float, str]] = []
        seen: set[str] = set()

        for query in queries:
            response = requests.post(
                "http://localhost:37777/search",
                json={"query": query, "limit": 4},
                timeout=3,
            )
            if not response.ok:
                continue

            for entry in response.json().get("results", []):
                summary = _normalize_mem_text(str(entry.get("summary", "")))
                if len(summary) < 25:
                    continue
                key = summary.lower()
                if key in seen:
                    continue
                seen.add(key)
                score = float(
                    entry.get("score")
                    or entry.get("similarity")
                    or entry.get("relevance")
                    or 0.0
                )
                ranked.append((score, summary))

        if not ranked:
            return None

        ranked.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
        parts: list[str] = []
        used = 0
        for _, summary in ranked[:5]:
            snippet = summary[:100].rstrip()
            if len(summary) > 100:
                snippet += "..."
            proposed = f"{' | ' if parts else ''}{snippet}"
            if used + len(proposed) > max_chars:
                break
            parts.append(snippet)
            used += len(proposed)

        return " | ".join(parts) if parts else None
    except Exception:
        return None


def _build_pipe_context(prompt: str, root: Path, max_bytes: int = 6_000) -> str:
    """
    For pipe mode: prepend CLAUDE.md + any files referenced in the prompt.

    This makes `ce run -p` self-contained so Claude gets project context and
    relevant file contents upfront in a single turn.
    """
    import re

    parts: list[str] = []
    total_bytes = 0

    claude_md = root / "CLAUDE.md"
    if claude_md.exists():
        md_text = claude_md.read_text(encoding="utf-8", errors="replace")[:2_000]
        parts.append(f"[Project context - CLAUDE.md]\n{md_text}")
        total_bytes += len(md_text.encode())

    file_pattern = re.compile(
        r"\b([\w./\\-]+\.(?:py|js|ts|tsx|jsx|go|rs|java|rb|toml|json|yaml|yml|sh|c|cpp|h))\b"
    )
    seen: set[str] = set()
    for match in file_pattern.findall(prompt):
        if match in seen or total_bytes >= max_bytes:
            break
        seen.add(match)
        candidate = (root / match).resolve()
        try:
            candidate.relative_to(root)
            if not candidate.is_file():
                continue
            content = candidate.read_text(encoding="utf-8", errors="replace")
            available = max_bytes - total_bytes
            snippet = content[:available]
            if not snippet:
                break
            ext = candidate.suffix.lstrip(".")
            parts.append(f"[{match}]\n```{ext}\n{snippet}\n```")
            total_bytes += len(snippet.encode())
        except (ValueError, OSError):
            continue

    if not parts:
        return prompt

    return "\n\n".join(parts) + "\n\n[Task]\n" + prompt
