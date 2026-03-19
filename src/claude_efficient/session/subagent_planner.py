from __future__ import annotations

import concurrent.futures
import re
import subprocess
import sys
from dataclasses import dataclass, field


@dataclass
class FileTask:
    target_file: str
    interface: str = ""
    depends_on: list[str] = field(default_factory=list)


@dataclass
class SubagentResult:
    file: str
    success: bool
    summary: str


def extract_file_targets(task_prompt: str) -> list[str]:
    """Extract file paths mentioned in a task prompt."""
    patterns = [
        r"(src/[\w/]+\.py)",
        r"([\w/]+/[\w]+\.py)",
        r"Build ([\w/\.]+)",
        r"Create ([\w/\.]+)",
    ]
    files: list[str] = []
    for p in patterns:
        files.extend(re.findall(p, task_prompt))
    return list(dict.fromkeys(files))   # dedup, preserve order


class SubagentPlanner:
    MAX_PARALLEL = 4

    def should_parallelize(self, task_prompt: str) -> bool:
        return len(extract_file_targets(task_prompt)) >= 2

    def build_waves(self, tasks: list[FileTask]) -> list[list[FileTask]]:
        """Topological sort into dependency waves."""
        waves: list[list[FileTask]] = []
        remaining = list(tasks)
        built: set[str] = set()

        while remaining:
            wave = [t for t in remaining if all(d in built for d in t.depends_on)]
            if not wave:
                wave = [remaining[0]]   # break cycle conservatively
            waves.append(wave)
            built.update(t.target_file for t in wave)
            remaining = [t for t in remaining if t not in wave]

        return waves

    def execute_wave(
        self,
        wave: list[FileTask],
        model: str = "claude-sonnet-4-6",
    ) -> list[SubagentResult]:
        """
        Execute a wave of independent tasks in parallel.
        model is fixed for all subagents — never switches mid-wave.
        """
        def run_task(task: FileTask) -> SubagentResult:
            interface_note = f"Interface contract: {task.interface}. " if task.interface else ""
            prompt = (
                f"Build {task.target_file}. "
                f"{interface_note}"
                f"See CLAUDE.md for project structure. "
                f"Output: file content only, no explanation, no preamble."
            )
            result = subprocess.run(
                ["claude", "--model", model, "-p", prompt],
                capture_output=True,
                text=True, encoding="utf-8", errors="replace",
                timeout=300,
                shell=(sys.platform == "win32"),
            )
            return SubagentResult(
                file=task.target_file,
                success=result.returncode == 0,
                summary=result.stdout[:500],
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.MAX_PARALLEL) as ex:
            return list(ex.map(run_task, wave))
