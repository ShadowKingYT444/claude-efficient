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


def route(task_prompt: str, task_shape: str | None = None) -> RoutingDecision:
    """
    Select model for the FULL session. This decision is made once, at session start.
    The chosen model must not change mid-session — doing so invalidates the prompt cache.

    task_shape: optional hint from classify_task_shape() for smarter routing.
    """
    # Shape-based routing (more accurate than keyword matching)
    if task_shape:
        if task_shape in ("explain", "system_design"):
            return RoutingDecision(
                model=OPUS,
                reason=f"task shape: {task_shape}",
                note="Full session on Opus — do not switch to Sonnet mid-session",
            )
        if task_shape in ("file_edit", "new_file"):
            return RoutingDecision(
                model=SONNET,
                reason=f"task shape: {task_shape}",
                note="Sonnet saves on output tokens; Opus savings disappear with cache hits",
            )

    # Fallback to keyword matching
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
