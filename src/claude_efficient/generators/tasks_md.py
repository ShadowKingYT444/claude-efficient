from pathlib import Path
import re

TASKS_MD_TEMPLATE = """\
# TASKS.md
**Maintained by claude-efficient. Start each session: "See TASKS.md. Build [next item]."**

## Current phase: Phase 1 — Setup

## Completed
- [x] INIT_01: Project initialized with claude-efficient

## Phase 1 — Setup
- [ ] SETUP_01: Define project goals and architecture
- [ ] SETUP_02: Implement core functionality
- [ ] SETUP_03: Add tests

## Phase 2 — Polish
- [ ] POLISH_01: Documentation
- [ ] POLISH_02: CI/CD setup
"""

_CHECKBOX_RE = re.compile(r"^(\s*-\s*\[)([ x])(\]\s*)(.+)$")


class TasksMdGenerator:
    def generate(self, root: Path) -> str:  # noqa: ARG002
        return TASKS_MD_TEMPLATE

    def update(
        self,
        root: Path,
        completed: list[str] | None = None,
        added: list[str] | None = None,
    ) -> str:
        """
        Read TASKS.md (or generate it), mark items done, append new items.
        Returns updated content without writing to disk.
        """
        path = root / "TASKS.md"
        content = path.read_text(encoding="utf-8") if path.exists() else self.generate(root)
        if completed:
            content = self._mark_completed(content, completed)
        if added:
            content = self._append_tasks(content, added)
        return content

    def write(self, root: Path, content: str) -> Path:
        out = root / "TASKS.md"
        out.write_text(content, encoding="utf-8")
        return out

    # ------------------------------------------------------------------
    def _mark_completed(self, content: str, names: list[str]) -> str:
        lines = content.splitlines()
        for i, line in enumerate(lines):
            m = _CHECKBOX_RE.match(line)
            if m and m.group(2) == " ":
                task_text = m.group(4)
                if any(n.lower() in task_text.lower() for n in names):
                    lines[i] = m.group(1) + "x" + m.group(3) + task_text
        return "\n".join(lines)

    def _append_tasks(self, content: str, tasks: list[str]) -> str:
        return content.rstrip("\n") + "\n" + "\n".join(tasks) + "\n"
