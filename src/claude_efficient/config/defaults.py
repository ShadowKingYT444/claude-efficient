"""Phase 3 + 6: HelperMode enum, input caps, and full HelpersConfig schema."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from claude_efficient.generators.backends import HelperTask


class HelperMode(str, Enum):
    off       = "off"
    safe_auto = "safe_auto"
    force     = "force"


CAPS: dict[HelperTask, int] = {
    HelperTask.project_digest_root:   12_000,
    HelperTask.project_digest_subdir:  4_000,
    HelperTask.prompt_normalize:       2_000,
    HelperTask.task_shape_classify:    2_000,
    HelperTask.mcp_relevance_classify: 1_000,
}


@dataclass
class GeminiConfig:
    enabled: bool = True
    model: str = "gemini-2.5-flash-lite"


@dataclass
class OllamaConfig:
    enabled: bool = True
    model: str = "qwen2.5:3b"
    fallback_model: str = "phi3:mini"


@dataclass
class OpenCodeConfig:
    enabled: bool = False
    command: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    model: str = ""


@dataclass
class HelpersConfig:
    mode: HelperMode = HelperMode.safe_auto
    default_backend: str = "gemini"
    auto_order: list[str] = field(default_factory=lambda: ["gemini", "ollama"])
    allow_tasks: list[str] = field(default_factory=lambda: [
        "project_digest_root", "project_digest_subdir",
        "prompt_normalize", "task_shape_classify", "mcp_relevance_classify",
    ])
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    opencode: OpenCodeConfig = field(default_factory=OpenCodeConfig)


class ConfigError(Exception):
    """Raised when a requested backend is not configured or available."""
