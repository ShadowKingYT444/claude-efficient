"""Phase 2: Backend selection logic."""
from __future__ import annotations

from claude_efficient.config.defaults import ConfigError, HelpersConfig
from claude_efficient.generators.backends import (
    DeterministicBackend,
    GeminiFlashLiteBackend,
    HelperBackend,
    HelperTask,
    OllamaBackend,
    OpenCodeBackend,
)


def _build_backend(name: str, config: HelpersConfig) -> HelperBackend:
    if name == "gemini":
        return GeminiFlashLiteBackend(model=config.gemini.model)
    if name == "ollama":
        return OllamaBackend(
            model=config.ollama.model,
            fallback_model=config.ollama.fallback_model,
        )
    if name == "opencode":
        return OpenCodeBackend(
            command=config.opencode.command,
            args=config.opencode.args,
            model=config.opencode.model,
        )
    if name == "deterministic":
        return DeterministicBackend()
    raise ConfigError(f"Unknown backend name: {name!r}")


def select_backend(
    config: HelpersConfig,
    task: HelperTask,
    override: str | None = None,
) -> HelperBackend:
    """
    Return the first available backend for the given task.

    override=None / "auto" → iterate config.auto_order, return first available.
    override=<name>        → use that backend; raise ConfigError if not available.

    Falls through to DeterministicBackend if nothing in auto_order is available.
    OpenCode is excluded from auto_order unless the user explicitly adds it.
    """
    if override and override != "auto":
        backend = _build_backend(override, config)
        if not backend.available():
            raise ConfigError(
                f"Backend {override!r} is not available. "
                "Check configuration and installed dependencies."
            )
        return backend

    for name in config.auto_order:
        backend = _build_backend(name, config)
        if task in backend.supported_tasks and backend.available():
            return backend

    return DeterministicBackend()
