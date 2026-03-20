"""Phase 4: ClaudeMdGenerator — deterministic-first, no raw file content paths."""
from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

from claude_efficient.generators.extractor import ExtractedFacts, SubdirCandidate

ALWAYS_SKIP = {
    "__pycache__", ".git", "node_modules", ".next", "dist", "build",
    ".ruff_cache", ".mypy_cache", "*.egg-info", ".venv", "venv",
}

SESSION_RULES = """\
## Session rules
- Code only. No preamble. No narration. One file per response.
- Never switch models mid-session (invalidates prompt cache).
- Prefer /clear + new session over /compact at natural breakpoints.
- Do not re-read files already shown in this conversation."""


def _build_precompact_command() -> str:
    script = (
        "from pathlib import Path; "
        "files = [('=== CRITICAL CONTEXT ===', Path('CLAUDE.md')), "
        "('=== CURRENT TASKS ===', Path('TASKS.md'))]; "
        "[(print(title), print(path.read_text(encoding='utf-8', errors='replace'))) "
        "for title, path in files if path.exists()]"
    )
    return f"{json.dumps(sys.executable)} -c {json.dumps(script)}"


PRECOMPACT_HOOK = {
    "hooks": {
        "PreCompact": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": _build_precompact_command(),
                    }
                ]
            }
        ]
    }
}


def write_claude_settings(root: Path) -> Path:
    """
    Write .claude/settings.json with PreCompact hook.
    Merges with existing file if present — never overwrites existing hooks.
    """
    claude_dir = root / ".claude"
    claude_dir.mkdir(exist_ok=True)
    settings_path = claude_dir / "settings.json"

    existing: dict = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except Exception:
            pass

    merged = {**existing}
    merged.setdefault("hooks", {})
    if "PreCompact" not in merged["hooks"]:
        merged["hooks"]["PreCompact"] = PRECOMPACT_HOOK["hooks"]["PreCompact"]

    settings_path.write_text(json.dumps(merged, indent=2))
    return settings_path


def _serialize_facts(facts: ExtractedFacts) -> str:
    """Serialize ExtractedFacts to compact text for helper input. No file contents included."""
    parts: list[str] = []
    if facts.tree:
        parts.append("STRUCTURE:\n" + "\n".join(facts.tree))
    if facts.languages:
        parts.append("LANGUAGES: " + ", ".join(facts.languages))
    if facts.commands:
        cmd_lines = "\n".join(f"  {k}: {v}" for k, v in facts.commands.items())
        parts.append("COMMANDS:\n" + cmd_lines)
    if facts.key_configs:
        parts.append("KEY CONFIGS:\n" + "\n".join(f"  {c}" for c in facts.key_configs))
    qualifying = [c for c in facts.subdir_candidates if c.qualifies]
    if qualifying:
        subdir_lines = "\n".join(
            f"  {c.path} ({c.language}, {c.file_count} files)" for c in qualifying
        )
        parts.append("QUALIFYING SUBDIRS:\n" + subdir_lines)
    return "\n\n".join(parts)


def _deterministic_root(facts: ExtractedFacts) -> str:
    lines: list[str] = ["# Project\n"]
    if facts.languages:
        lines.append("## Languages\n" + ", ".join(facts.languages) + "\n")
    if facts.commands:
        lines.append("## Commands")
        for k, v in facts.commands.items():
            lines.append(f"- {k}: `{v}`")
        lines.append("")
    if facts.tree:
        lines.append("## Structure")
        lines.extend(facts.tree[:15])
        lines.append("")
    if facts.key_configs:
        lines.append("## Key configs")
        lines.extend(f"- {c}" for c in facts.key_configs[:12])
        lines.append("")
    lines.append(SESSION_RULES)
    return "\n".join(lines)


def _deterministic_subdir(candidate: SubdirCandidate) -> str:
    return (
        f"# {candidate.path}\n\n"
        f"{candidate.language} subdir with {candidate.file_count} source files."
    )


class ClaudeMdGenerator:
    MAX_BYTES = 2_000
    SUBDIR_MAX_BYTES = 600

    def generate_root(
        self,
        facts: ExtractedFacts,
        *,
        invoke_helper_fn: Callable[[str], str | None] | None,
    ) -> str:
        """
        Generate root CLAUDE.md from extracted facts.

        invoke_helper_fn receives the serialized ExtractedFacts (no raw file contents).
        Returns None to signal fallback; ClaudeMdGenerator then uses deterministic rendering.
        """
        result: str | None = None
        if invoke_helper_fn is not None:
            result = invoke_helper_fn(_serialize_facts(facts))
        if result is None:
            result = _deterministic_root(facts)
        if len(result.encode()) > self.MAX_BYTES:
            result = self._trim(result)
        return result

    def generate_subdir(
        self,
        candidate: SubdirCandidate,
        *,
        invoke_helper_fn: Callable[[str], str | None] | None,
    ) -> str:
        """
        Generate subdir CLAUDE.md. Returns the content string.
        invoke_helper_fn returns None to signal fallback.
        """
        content_input = (
            f"SUBDIR: {candidate.path}\n"
            f"LANGUAGE: {candidate.language}\n"
            f"FILES: {candidate.file_count}"
        )
        result: str | None = None
        if invoke_helper_fn is not None:
            result = invoke_helper_fn(content_input)
        if result is None:
            result = _deterministic_subdir(candidate)
        encoded = result.encode("utf-8")
        if len(encoded) > self.SUBDIR_MAX_BYTES:
            result = encoded[:self.SUBDIR_MAX_BYTES].decode("utf-8", errors="ignore")
        return result

    def write(self, root: Path, content: str) -> Path:
        out = root / "CLAUDE.md"
        out.write_text(content, encoding="utf-8")
        return out

    def write_gemini_md(self, root: Path, content: str) -> Path:
        out = root / "GEMINI.md"
        out.write_text(content.replace("CLAUDE.md", "GEMINI.md"), encoding="utf-8")
        return out

    def _trim(self, content: str) -> str:
        """Trim key files list until under MAX_BYTES. Never trim commands section."""
        lines = content.splitlines()
        while len("\n".join(lines).encode()) > self.MAX_BYTES and len(lines) > 1:
            lines.pop(-2)
        if len("\n".join(lines).encode()) > self.MAX_BYTES:
            encoded = "\n".join(lines).encode()
            return encoded[:self.MAX_BYTES].decode(errors="ignore")
        return "\n".join(lines)
