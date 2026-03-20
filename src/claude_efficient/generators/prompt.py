"""Phase 5: Prompt normalization and task shape classification."""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class TaskShape:
    shape: str       # "file_edit" | "new_file" | "refactor" | "explain" | "unknown"
    confidence: float  # 0.0–1.0; routing hints only; guardrails ignore below 0.5


_VALID_SHAPES = {"file_edit", "new_file", "refactor", "explain", "unknown"}


def normalize_prompt(
    raw: str,
    *,
    invoke_helper_fn: Callable[[str], str] | None,
) -> str:
    """
    Clean up raw prompt before passing to ce run core logic.
    Helper is used for normalization; deterministic fallback is strip().
    Input cap: 2 KB (enforced by orchestrator, not here).
    """
    if invoke_helper_fn is None:
        return raw.strip()
    result = invoke_helper_fn(raw)
    return result.strip() if result else raw.strip()


def classify_task_shape(
    prompt: str,
    *,
    invoke_helper_fn: Callable[[str], str] | None,
) -> TaskShape:
    """
    Classify task type for model routing hints.
    Helper output is advisory only — routing guardrails use it as a hint,
    not a binding decision.
    Deterministic fallback: TaskShape(shape="unknown", confidence=0.0)
    """
    if invoke_helper_fn is None:
        return TaskShape(shape="unknown", confidence=0.0)
    try:
        raw = invoke_helper_fn(prompt)
        return _parse_shape(raw)
    except Exception:
        return TaskShape(shape="unknown", confidence=0.0)


def _parse_shape(text: str) -> TaskShape:
    """Parse helper output into a TaskShape. Conservative: unknown on any ambiguity."""
    text_lower = text.strip().lower()
    for shape in _VALID_SHAPES:
        if shape in text_lower:
            m = re.search(r"\b(0?\.\d+|1\.0)\b", text_lower)
            confidence = float(m.group(1)) if m else 0.7
            return TaskShape(shape=shape, confidence=min(confidence, 1.0))
    return TaskShape(shape="unknown", confidence=0.0)
