"""Phase 6: Config loading and resolve_helpers_config."""
from __future__ import annotations

from pathlib import Path

from claude_efficient.config.defaults import (
    ConfigError,
    GeminiConfig,
    HelpersConfig,
    HelperMode,
    OllamaConfig,
    OpenCodeConfig,
)
from claude_efficient.generators.backends import HelperBackend, HelperTask
from claude_efficient.generators.selector import select_backend


def _load_project_config(project_root: Path) -> dict:
    config_file = project_root / ".claude-efficient.toml"
    if not config_file.exists():
        return {}
    try:
        import tomllib
        with open(config_file, "rb") as f:
            return tomllib.load(f).get("helpers", {})
    except Exception:
        return {}


def _merge_config(project_helpers: dict) -> HelpersConfig:
    cfg = HelpersConfig()
    if not project_helpers:
        return cfg

    mode_str = project_helpers.get("mode")
    if mode_str:
        try:
            cfg.mode = HelperMode(mode_str)
        except ValueError:
            pass

    if "default_backend" in project_helpers:
        cfg.default_backend = project_helpers["default_backend"]
    if "auto_order" in project_helpers:
        cfg.auto_order = list(project_helpers["auto_order"])
    if "allow_tasks" in project_helpers:
        cfg.allow_tasks = list(project_helpers["allow_tasks"])

    gemini_cfg = project_helpers.get("gemini", {})
    if gemini_cfg:
        cfg.gemini = GeminiConfig(
            enabled=gemini_cfg.get("enabled", True),
            model=gemini_cfg.get("model", "gemini-2.5-flash-lite"),
        )

    ollama_cfg = project_helpers.get("ollama", {})
    if ollama_cfg:
        cfg.ollama = OllamaConfig(
            enabled=ollama_cfg.get("enabled", True),
            model=ollama_cfg.get("model", "qwen2.5:3b"),
            fallback_model=ollama_cfg.get("fallback_model", "phi3:mini"),
        )

    opencode_cfg = project_helpers.get("opencode", {})
    if opencode_cfg:
        cfg.opencode = OpenCodeConfig(
            enabled=opencode_cfg.get("enabled", False),
            command=opencode_cfg.get("command", []),
            args=opencode_cfg.get("args", []),
            model=opencode_cfg.get("model", ""),
        )

    return cfg


def resolve_helpers_config(
    helpers_override: str | None,
    backend_override: str | None,
    project_root: Path | None = None,
) -> tuple[HelperMode, HelperBackend]:
    """
    Resolve final mode + backend.
    Precedence: CLI flag > project config > defaults.

    helpers_override: "off" | "auto" | "force" | None
    backend_override: "auto" | "gemini" | "ollama" | "opencode" | None
    """
    project_helpers = _load_project_config(project_root) if project_root else {}
    config = _merge_config(project_helpers)

    if helpers_override == "off":
        config.mode = HelperMode.off
    elif helpers_override == "auto":
        config.mode = HelperMode.safe_auto
    elif helpers_override == "force":
        config.mode = HelperMode.force

    if backend_override == "opencode":
        if (
            not config.opencode.enabled
            or not config.opencode.command
            or not config.opencode.model
        ):
            raise ConfigError(
                "opencode backend requires [helpers.opencode] enabled = true, "
                "command, and model to be set in .claude-efficient.toml"
            )

    backend = select_backend(
        config,
        HelperTask.project_digest_root,
        override=backend_override,
    )
    return config.mode, backend
