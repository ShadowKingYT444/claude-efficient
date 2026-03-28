"""Output token budgeting based on task analysis.

Estimates appropriate output budget and encodes it as a prompt suffix.
Claude won't enforce hard limits, but including budgets creates a strong
prior toward concise output -- the single highest-impact token saving.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OutputBudget:
    estimated_tokens: int
    hint: str


def estimate_output_budget(task: str, file_count: int = 1) -> OutputBudget:
    """Compute suggested output token budget based on task analysis."""
    lower = task.lower()

    if any(w in lower for w in ("explain", "what does", "how does", "why")):
        return OutputBudget(300, "Max 3 bullet points, 15 words each.")

    if any(w in lower for w in ("fix", "bug", "error", "broken", "failing")):
        return OutputBudget(500 * file_count, f"Minimal diff only. ~{file_count} file(s).")

    if any(w in lower for w in ("refactor", "rename", "move", "reorganize")):
        return OutputBudget(800 * file_count, f"Diffs only, {file_count} file(s). No narration.")

    if any(w in lower for w in ("add", "create", "build", "implement", "new")):
        return OutputBudget(2000 * min(file_count, 3), "Code blocks only. No step-by-step.")

    return OutputBudget(1000, "Be concise. Code only where possible.")


def format_budget_hint(budget: OutputBudget) -> str:
    """Format as a prompt suffix."""
    return f"\n[Output budget: ~{budget.estimated_tokens} tokens. {budget.hint}]"
