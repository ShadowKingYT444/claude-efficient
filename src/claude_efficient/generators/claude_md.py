"""Phase 4: ClaudeMdGenerator — deterministic-first, no raw file content paths."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from claude_efficient.generators.architecture import (
    ArchitectureMap,
    generate_anti_exploration,
    render_architecture_md,
)
from claude_efficient.generators.extractor import ExtractedFacts, SubdirCandidate

ALWAYS_SKIP = {
    "__pycache__", ".git", "node_modules", ".next", "dist", "build",
    ".ruff_cache", ".mypy_cache", "*.egg-info", ".venv", "venv",
}

SESSION_RULES = """\
## MANDATORY OUTPUT FORMAT (violations waste tokens = waste money)

### Response Structure (EVERY response must follow this)
1. Tool calls OR code blocks. Nothing else.
2. NO explanations before code. NO summaries after code.
3. NO "Let me...", "I'll...", "Here's...", "Now I'll..." preamble.
4. NO "I've completed...", "This should...", "The changes..." postamble.
5. If asked to explain: bullet points only, max 3 bullets, max 15 words each.

### File Operations
- Before reading ANY file: check if its path+purpose is documented above.
  If documented, skip the read unless you need exact line numbers.
- Never re-read a file already shown in this conversation.
- Never read files listed in "Skip These Files" section.
- Batch all related file reads into one turn (parallel tool calls).

### Code Output
- Write the minimal diff. Don't rewrite unchanged code.
- No comments explaining what the code does (the code IS the explanation).
- No type annotations unless the project already uses them.
- No docstrings unless the project already has them.

### Tool Call Discipline
- Batch file reads: read all needed files in ONE turn (parallel tool calls).
- Don't read a file just to check one thing — grep for it instead.
- Don't run tests after every small change — batch changes, test once.
- If a command fails, fix the root cause; don't retry the same command.
- Prefer Edit over Write for existing files (smaller diffs = fewer tokens).

### Session Management
- Never switch models mid-session (invalidates prompt cache).
- Prefer /clear + new session over /compact at natural breakpoints.
- If you've made 3+ tool calls without writing code, stop exploring and start writing."""


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
    """Serialize ExtractedFacts to compact text for helper input."""
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
    if facts.key_file_contents:
        file_contents = []
        for path, content in facts.key_file_contents.items():
            file_contents.append(f"--- {path} ---\n{content}")
        parts.append("KEY FILE CONTENTS:\n" + "\n".join(file_contents))
    qualifying = [c for c in facts.subdir_candidates if c.qualifies]
    if qualifying:
        subdir_lines = "\n".join(
            f"  {c.path} ({c.language}, {c.file_count} files)" for c in qualifying
        )
        parts.append("QUALIFYING SUBDIRS:\n" + subdir_lines)
    return "\n\n".join(parts)


def _deterministic_root(facts: ExtractedFacts, arch: ArchitectureMap | None = None) -> str:
    lines: list[str] = ["# Project\n"]
    if facts.languages:
        lines.append("## Languages\n" + ", ".join(facts.languages) + "\n")
    if facts.commands:
        lines.append("## Commands")
        for k, v in facts.commands.items():
            lines.append(f"- {k}: `{v}`")
        lines.append("")
    if arch:
        arch_md = render_architecture_md(arch)
        if arch_md.strip():
            lines.append(arch_md)
    else:
        if facts.tree:
            lines.append("## Structure")
            lines.extend(facts.tree[:15])
            lines.append("")
    if facts.key_configs:
        lines.append("## Key configs")
        lines.extend(f"- {c}" for c in facts.key_configs[:12])
        lines.append("")
    lines.append(SESSION_RULES)
    if arch:
        lines.append("\n" + generate_anti_exploration(arch))
    return "\n".join(lines)


def _deterministic_subdir(candidate: SubdirCandidate) -> str:
    lines = [
        f"# {candidate.path}\n",
        f"{candidate.language} subdir with {candidate.file_count} source files."
    ]
    if candidate.files:
        lines.append("\n## Key Files")
        for f, desc in candidate.files.items():
            lines.append(f"- {f}: {desc}" if desc else f"- {f}")
    return "\n".join(lines)


class ClaudeMdGenerator:
    MAX_BYTES = 8_000
    SUBDIR_MAX_BYTES = 4_000

    def render_facts_to_prompt(self, facts: ExtractedFacts) -> str:
        """Renders extracted facts into a structured prompt for an LLM."""
        return (
            "You are generating a CLAUDE.md file for an AI coding assistant. "
            "Output ONLY valid Markdown (no JSON/YAML wrappers). Include the project structure, languages, commands, "
            "and briefly describe the purpose of each key file based on the provided names/descriptions and their content.\n\n"
            "## Extracted Facts:\n"
            + _serialize_facts(facts)
        )

    def generate_root(
        self,
        facts: ExtractedFacts,
        project_summary: str | None,
        arch: ArchitectureMap | None = None,
    ) -> str:
        """
        Generate root CLAUDE.md from extracted facts.
        Uses project_summary from helper if provided, otherwise deterministic.
        If arch is provided, enriches output with deep architecture map + anti-exploration.
        """
        if project_summary:
            result = project_summary
            # Even with a helper summary, append anti-exploration if architecture available
            if arch:
                result += "\n\n" + generate_anti_exploration(arch)
        else:
            result = _deterministic_root(facts, arch)
        if len(result.encode()) > self.MAX_BYTES:
            result = self._trim(result)
        return result

    def render_subdir_facts_to_prompt(self, candidate: SubdirCandidate) -> str:
        """Renders subdirectory facts into a structured prompt for an LLM."""
        prompt = (
            "You are generating a subdir-level CLAUDE.md file for an AI assistant. "
            "Output ONLY valid Markdown (no JSON/YAML wrappers). List the files and briefly describe what this subdirectory and its files are responsible for.\n\n"
            f"SUBDIR: {candidate.path}\n"
            f"LANGUAGE: {candidate.language}\n"
            f"FILES: {candidate.file_count}\n"
            f"DESCRIPTIONS:\n" + "\n".join(f"  {f}: {d}" if d else f"  {f}" for f, d in candidate.files.items())
        )
        if candidate.key_file_contents:
            key_contents = []
            for path, content in candidate.key_file_contents.items():
                key_contents.append(f"--- {path} ---\n{content}")
            prompt += "\n\nKEY FILE CONTENTS:\n" + "\n".join(key_contents)
        return prompt

    def generate_subdir(
        self,
        candidate: SubdirCandidate,
        subdir_summary: str | None,
    ) -> str:
        """
        Generate subdir CLAUDE.md. Returns the content string.
        """
        result = subdir_summary if subdir_summary else _deterministic_subdir(candidate)
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

    def write_agents_md(self, root: Path, content: str) -> Path:
        out = root / "AGENTS.md"
        out.write_text(content.replace("CLAUDE.md", "AGENTS.md"), encoding="utf-8")
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
