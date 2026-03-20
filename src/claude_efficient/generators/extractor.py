"""Phase 4: Deterministic project fact extraction. No file contents are read."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ALWAYS_SKIP = {
    "__pycache__", ".git", "node_modules", ".next", "dist", "build",
    ".ruff_cache", ".mypy_cache", ".venv", "venv",
}

LANGUAGE_EXTENSIONS: dict[str, set[str]] = {
    "python":     {".py"},
    "typescript": {".ts", ".tsx", ".js", ".jsx"},
    "go":         {".go"},
    "rust":       {".rs"},
}

QUALIFY_THRESHOLDS: dict[str, int] = {
    "python":     5,
    "typescript": 5,
    "go":         3,
    "rust":       3,
}

KEY_CONFIG_NAMES = {
    "pyproject.toml", "package.json", "go.mod", "Cargo.toml",
    "Makefile", "setup.py", "setup.cfg", "requirements.txt",
    ".env.example", "docker-compose.yml", "Dockerfile",
    "tsconfig.json", ".eslintrc.json", "jest.config.js",
}


@dataclass
class SubdirCandidate:
    path: str
    language: str
    file_count: int
    qualifies: bool


@dataclass
class ExtractedFacts:
    tree: list[str] = field(default_factory=list)
    commands: dict[str, str] = field(default_factory=dict)
    languages: list[str] = field(default_factory=list)
    key_configs: list[str] = field(default_factory=list)
    subdir_candidates: list[SubdirCandidate] = field(default_factory=list)


def extract_facts(project_root: Path) -> ExtractedFacts:
    return ExtractedFacts(
        tree=_scan_tree(project_root),
        commands=_extract_commands(project_root),
        languages=_detect_languages(project_root),
        key_configs=_find_key_configs(project_root),
        subdir_candidates=_find_subdir_candidates(project_root),
    )


def _scan_tree(root: Path, max_entries: int = 15) -> list[str]:
    entries: list[str] = []
    try:
        for entry in sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name)):
            if entry.name in ALWAYS_SKIP or entry.name.startswith("."):
                continue
            rel = entry.relative_to(root)
            entries.append(f"{rel}/" if entry.is_dir() else str(rel))
            if len(entries) >= max_entries:
                break
    except (PermissionError, OSError):
        pass
    return entries


def _detect_languages(root: Path) -> list[str]:
    counts: dict[str, int] = {}
    try:
        for f in root.rglob("*"):
            if not f.is_file():
                continue
            if any(skip in f.parts for skip in ALWAYS_SKIP):
                continue
            for lang, exts in LANGUAGE_EXTENSIONS.items():
                if f.suffix in exts:
                    counts[lang] = counts.get(lang, 0) + 1
    except (PermissionError, OSError):
        pass
    return [lang for lang, _ in sorted(counts.items(), key=lambda x: -x[1])]


def _find_key_configs(root: Path, max_configs: int = 12) -> list[str]:
    configs: list[str] = []
    try:
        for entry in root.iterdir():
            if entry.name in KEY_CONFIG_NAMES and entry.is_file():
                configs.append(str(entry.relative_to(root)))
    except (PermissionError, OSError):
        pass
    return sorted(configs)[:max_configs]


def _find_subdir_candidates(root: Path) -> list[SubdirCandidate]:
    candidates: list[SubdirCandidate] = []
    try:
        subdirs = [
            d for d in sorted(root.rglob("*/"))
            if d.is_dir() and not any(skip in d.parts for skip in ALWAYS_SKIP)
        ]
    except (PermissionError, OSError):
        return []
    for subdir in subdirs:
        for lang, exts in LANGUAGE_EXTENSIONS.items():
            count = 0
            for ext in exts:
                try:
                    count += sum(1 for _ in subdir.glob(f"*{ext}"))
                except (PermissionError, OSError):
                    pass
            if count > 0:
                candidates.append(SubdirCandidate(
                    path=str(subdir.relative_to(root)).replace("\\", "/"),
                    language=lang,
                    file_count=count,
                    qualifies=count >= QUALIFY_THRESHOLDS[lang],
                ))
    return candidates


def _extract_commands(root: Path) -> dict[str, str]:
    cmds: dict[str, str] = {}

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            import tomllib
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
            scripts = (
                data.get("tool", {}).get("poetry", {}).get("scripts", {})
                or data.get("project", {}).get("scripts", {})
            )
            if scripts:
                cmds.setdefault("run", next(iter(scripts)))
            if data.get("tool", {}).get("pytest") is not None or "pytest" in str(
                data.get("project", {}).get("dependencies", [])
            ):
                cmds.setdefault("test", "pytest tests/ -x")
            if data.get("tool", {}).get("ruff") is not None:
                cmds.setdefault("lint", "ruff check .")
        except Exception:
            pass

    pkg_json = root / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8", errors="replace"))
            scripts = data.get("scripts", {})
            for cmd, key in [
                ("run", "start"), ("run", "dev"), ("test", "test"),
                ("build", "build"), ("lint", "lint"),
            ]:
                if key in scripts:
                    cmds.setdefault(cmd, f"npm run {key}")
        except Exception:
            pass

    if (root / "go.mod").exists():
        cmds.setdefault("run", "go run .")
        cmds.setdefault("test", "go test ./...")
        cmds.setdefault("build", "go build ./...")

    if (root / "Cargo.toml").exists():
        cmds.setdefault("run", "cargo run")
        cmds.setdefault("test", "cargo test")
        cmds.setdefault("build", "cargo build")
        cmds.setdefault("lint", "cargo clippy")

    if (root / "Makefile").exists() and not cmds:
        cmds["build"] = "make"

    return cmds
