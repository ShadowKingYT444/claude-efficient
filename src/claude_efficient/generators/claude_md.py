import json
from pathlib import Path

from claude_efficient.generators.backends import Backend

CLAUDE_MD_PROMPT = """\
Generate a CLAUDE.md file for this project. Output ONLY raw markdown, no explanation.
Hard constraints:
- Total output under 2000 bytes
- Folder map: max 15 entries, format: `path/  # one-line purpose`
- Key files: max 10, include WHY each matters
- Run commands: auto-detect from pyproject.toml / Makefile / package.json
- End with this exact block:
  ## Output format
  Code only. No preamble. No narration. One file per response.
"""

ALWAYS_SKIP = {
    "__pycache__", ".git", "node_modules", ".next", "dist", "build",
    ".ruff_cache", ".mypy_cache", "*.egg-info", ".venv", "venv",
}
KEY_FILE_NAMES = {
    "pyproject.toml", "package.json", "Makefile", "setup.py",
    "setup.cfg", "requirements.txt", "config.py", "settings.py",
    "main.py", "app.py", "index.py", "__init__.py",
}

PRECOMPACT_HOOK = {
    "hooks": {
        "PreCompact": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": (
                            "echo '=== CRITICAL CONTEXT ===' && cat CLAUDE.md && "
                            "echo '=== CURRENT TASKS ===' && cat TASKS.md 2>/dev/null || true"
                        ),
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

    # Merge: don't clobber existing hooks
    merged = {**existing}
    merged.setdefault("hooks", {})
    if "PreCompact" not in merged["hooks"]:
        merged["hooks"]["PreCompact"] = PRECOMPACT_HOOK["hooks"]["PreCompact"]

    settings_path.write_text(json.dumps(merged, indent=2))
    return settings_path


class ClaudeMdGenerator:
    MAX_BYTES = 2_000
    MAX_KEY_FILES = 10
    MAX_DEPTH = 3

    SUBDIR_PROMPT = """\
Generate a minimal CLAUDE.md for this subdirectory. Output ONLY raw markdown, no explanation.
Constraints:
- Total output under 600 bytes
- Focus ONLY on what is unique to this subdirectory: its purpose, key interfaces, gotchas
- Do NOT repeat project-level information already in the root CLAUDE.md
- No folder map, no run commands — those are in the root
"""

    def scan_structure(self, root: Path) -> tuple[str, list[Path]]:
        """Returns (file_tree_str, key_file_paths)."""
        tree_lines = []
        key_files = []
        self._walk(root, root, 0, tree_lines, key_files)
        return "\n".join(tree_lines), key_files[:self.MAX_KEY_FILES]

    def _walk(self, root, current, depth, tree_lines, key_files):
        if depth > self.MAX_DEPTH:
            return
        try:
            entries = sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return
        for entry in entries:
            if entry.name in ALWAYS_SKIP or entry.name.startswith("."):
                continue
            rel = entry.relative_to(root)
            indent = "  " * depth
            if entry.is_dir():
                tree_lines.append(f"{indent}{rel}/")
                self._walk(root, entry, depth + 1, tree_lines, key_files)
            else:
                tree_lines.append(f"{indent}{rel}")
                if entry.name in KEY_FILE_NAMES and len(key_files) < self.MAX_KEY_FILES:
                    key_files.append(entry)

    def generate(self, root: Path, backend: Backend) -> str:
        file_tree, key_files = self.scan_structure(root)
        payload = backend._build_payload(root, file_tree, key_files)
        result = backend.summarize(CLAUDE_MD_PROMPT, payload)
        if len(result.encode()) > self.MAX_BYTES:
            result = self._trim(result)
        return result

    def write(self, root: Path, content: str) -> Path:
        out = root / "CLAUDE.md"
        out.write_text(content, encoding="utf-8")
        return out

    def write_gemini_md(self, root: Path, content: str) -> Path:
        """Same content, different filename for Gemini CLI sessions."""
        out = root / "GEMINI.md"
        out.write_text(content.replace("CLAUDE.md", "GEMINI.md"), encoding="utf-8")
        return out

    def _trim(self, content: str) -> str:
        """Trim key files list until under MAX_BYTES. Never trim commands section."""
        lines = content.splitlines()
        while len("\n".join(lines).encode()) > self.MAX_BYTES and len(lines) > 1:
            lines.pop(-2)
        if len("\n".join(lines).encode()) > self.MAX_BYTES:
            # Single long line — hard truncate
            encoded = "\n".join(lines).encode()
            return encoded[:self.MAX_BYTES].decode(errors="ignore")
        return "\n".join(lines)

    def generate_import_tree(
        self,
        root: Path,
        backend: "Backend",
        min_py_files: int = 3,
        max_subdirs: int = 5,
    ) -> str:
        """
        Generate CLAUDE.md in each qualifying subdirectory and return an
        @import block ready to append to the root CLAUDE.md.

        A subdir qualifies if it contains >= min_py_files .py files.
        Returns empty string if no qualifying subdirs found.
        """
        candidates = [
            d for d in sorted(root.rglob("*/"))
            if d.is_dir()
            and not any(skip in d.parts for skip in ALWAYS_SKIP)
            and len(list(d.glob("*.py"))) >= min_py_files
        ][:max_subdirs]

        if not candidates:
            return ""

        import_lines = ["\n## Subdirectory context (auto-loaded by Claude Code)", ""]
        for subdir in candidates:
            rel = subdir.relative_to(root)
            file_tree, key_files = self.scan_structure(subdir)
            payload = backend._build_payload(subdir, file_tree, key_files, max_files=5)
            content = backend.summarize(self.SUBDIR_PROMPT, payload)
            # Hard-trim to 600 bytes
            encoded = content.encode("utf-8")
            if len(encoded) > 600:
                content = encoded[:600].decode("utf-8", errors="ignore")
            (subdir / "CLAUDE.md").write_text(content, encoding="utf-8")
            import_lines.append(f"@{rel}/CLAUDE.md")

        return "\n".join(import_lines)
