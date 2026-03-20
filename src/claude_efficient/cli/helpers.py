"""Phase 6: `ce helpers` subcommand — provider status and config inspection."""
from __future__ import annotations

from pathlib import Path

import click

from claude_efficient.config.loader import _load_project_config, _merge_config
from claude_efficient.generators.backends import (
    GeminiFlashLiteBackend,
    HelperTask,
    OllamaBackend,
    OpenCodeBackend,
)
from claude_efficient.generators.selector import select_backend


@click.command("helpers")
@click.option("--root", default=".", type=click.Path())
def helpers_cmd(root: str) -> None:
    """Show helper provider status and active configuration."""
    root_path = Path(root).resolve()

    project_helpers = _load_project_config(root_path)
    config = _merge_config(project_helpers)

    click.echo("\nDetected providers:")

    # Gemini
    gemini = GeminiFlashLiteBackend(model=config.gemini.model)
    if not config.gemini.enabled:
        _row("gemini", "disabled", config.gemini.model, "disabled in config")
    elif gemini.available():
        _row("gemini", "available", config.gemini.model, "GEMINI_API_KEY set")
    else:
        _row("gemini", "unavailable", config.gemini.model, "GEMINI_API_KEY not set")

    # Ollama
    ollama = OllamaBackend(
        model=config.ollama.model,
        fallback_model=config.ollama.fallback_model,
    )
    if not config.ollama.enabled:
        _row("ollama", "disabled", config.ollama.model, "disabled in config")
    elif ollama.available():
        _row("ollama", "available", config.ollama.model, "running at localhost:11434")
    else:
        _row("ollama", "unavailable", config.ollama.model, "connection refused at localhost:11434")

    # OpenCode
    if not config.opencode.enabled:
        _row("opencode", "disabled", "n/a", "not configured")
    elif not config.opencode.command or not config.opencode.model:
        _row("opencode", "misconfigured", "n/a", "command or model is empty — set [helpers.opencode]")
    else:
        oc = OpenCodeBackend(
            command=config.opencode.command,
            args=config.opencode.args,
            model=config.opencode.model,
        )
        if oc.available():
            _row("opencode", "available", config.opencode.model, "")
        else:
            _row("opencode", "unavailable", config.opencode.model, "command not found in PATH")

    source = "project" if project_helpers else "defaults"
    click.echo(f"\nActive config ({source}):")
    click.echo(f"  mode           = {config.mode.value}")
    click.echo(f"  default_backend= {config.default_backend}")
    click.echo(f"  auto_order     = {config.auto_order!r}")

    try:
        selected = select_backend(config, HelperTask.project_digest_root)
        click.echo(f"\nSelected default: {selected.name}")
    except Exception:
        click.echo("\nSelected default: deterministic (fallback)")

    if not config.opencode.enabled:
        click.echo(
            "\nNote: opencode requires [helpers.opencode] command, args, and model to be set."
        )


def _row(name: str, status: str, model: str, note: str) -> None:
    note_str = f"  ({note})" if note else ""
    click.echo(f"  {name:<10}{status:<14}{model:<24}{note_str}")
