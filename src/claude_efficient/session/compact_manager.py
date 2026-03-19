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
