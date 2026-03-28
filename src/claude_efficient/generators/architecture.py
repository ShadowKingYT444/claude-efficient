"""Deep architecture extraction for CLAUDE.md generation.

Instead of listing files, this module extracts:
1. Module purposes (from docstrings, __init__.py, class/function names)
2. Dependency graph (which modules import which)
3. Entry points and data flow
4. Common patterns (decorator usage, base classes, error handling)
5. Files that should NOT be read (generated, large, historical)

The goal: Claude should be able to make most edits WITHOUT reading
any files first, because CLAUDE.md tells it exactly where things are
and what patterns to follow.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {
    "__pycache__", ".git", "node_modules", ".venv", "venv",
    "dist", "build", ".egg-info", "migrations", ".next",
    ".ruff_cache", ".mypy_cache",
}


@dataclass
class ModuleInfo:
    path: str
    purpose: str
    public_api: list[str]
    imports_from: list[str]
    line_count: int
    complexity: str  # "trivial" | "simple" | "moderate" | "complex"


@dataclass
class ArchitectureMap:
    layers: dict[str, list[ModuleInfo]] = field(default_factory=dict)
    entry_points: list[str] = field(default_factory=list)
    common_patterns: list[str] = field(default_factory=list)
    skip_files: list[str] = field(default_factory=list)
    dependency_flow: list[str] = field(default_factory=list)


def extract_architecture(root: Path) -> ArchitectureMap:
    """Walk the project and build a high-level architecture map."""
    modules = _discover_modules(root)
    layers = _classify_into_layers(modules)
    entry_points = _find_entry_points(modules)
    patterns = _detect_common_patterns(root, modules)
    skip_files = _find_skip_candidates(root, modules)
    dep_flow = _build_dependency_flow(layers)

    return ArchitectureMap(
        layers=layers,
        entry_points=entry_points,
        common_patterns=patterns,
        skip_files=skip_files,
        dependency_flow=dep_flow,
    )


def _discover_modules(root: Path) -> list[ModuleInfo]:
    """Extract ModuleInfo from every Python file via AST analysis."""
    modules = []
    for py_file in root.rglob("*.py"):
        if any(skip in py_file.parts for skip in SKIP_DIRS):
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content)

            docstring = ast.get_docstring(tree) or ""
            purpose = docstring.split("\n")[0][:100] if docstring else ""

            if not purpose:
                purpose = _infer_purpose(tree, py_file.name)

            public = []
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                    public.append(f"class {node.name}")
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not node.name.startswith("_"):
                        public.append(f"{node.name}()")

            imports_from = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    if not node.module.startswith(("os", "sys", "re", "json", "typing",
                                                    "pathlib", "dataclasses", "enum",
                                                    "collections", "functools")):
                        imports_from.append(node.module)

            line_count = len(content.splitlines())
            complexity = (
                "trivial" if line_count < 30 else
                "simple" if line_count < 100 else
                "moderate" if line_count < 300 else
                "complex"
            )

            modules.append(ModuleInfo(
                path=str(py_file.relative_to(root)).replace("\\", "/"),
                purpose=purpose,
                public_api=public[:10],
                imports_from=imports_from,
                line_count=line_count,
                complexity=complexity,
            ))
        except Exception:
            continue

    return modules


def _infer_purpose(tree: ast.Module, filename: str) -> str:
    """Infer module purpose from its contents when no docstring exists."""
    classes = [n.name for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef)]
    functions = [n.name for n in ast.iter_child_nodes(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

    if classes:
        return f"Defines {', '.join(classes[:3])}"
    if functions:
        return f"Contains {', '.join(functions[:3])}"
    return f"Module: {filename}"


def _classify_into_layers(modules: list[ModuleInfo]) -> dict[str, list[ModuleInfo]]:
    """Group modules into architectural layers based on path and content."""
    layer_hints = {
        "api": ["api", "routes", "endpoints", "views", "handlers"],
        "cli": ["cli", "commands", "main"],
        "services": ["services", "logic", "core", "domain"],
        "generators": ["generators", "render", "template"],
        "models": ["models", "schemas", "entities", "types"],
        "data": ["db", "database", "repository", "dao", "store"],
        "analysis": ["analysis", "metrics", "telemetry", "monitor"],
        "session": ["session", "router", "planner"],
        "config": ["config", "settings", "constants"],
        "utils": ["utils", "helpers", "common", "shared"],
        "tests": ["tests", "test_"],
    }

    layers: dict[str, list[ModuleInfo]] = {}
    for mod in modules:
        path_lower = mod.path.lower()
        assigned = False
        for layer, hints in layer_hints.items():
            if any(h in path_lower for h in hints):
                layers.setdefault(layer, []).append(mod)
                assigned = True
                break
        if not assigned:
            layers.setdefault("other", []).append(mod)

    return layers


def _find_entry_points(modules: list[ModuleInfo]) -> list[str]:
    """Find likely entry points (main functions, CLI commands, app factories)."""
    entry_points = []
    for mod in modules:
        for api in mod.public_api:
            if any(name in api.lower() for name in ("main", "cli", "app", "run", "start")):
                entry_points.append(f"{mod.path}:{api}")
    return entry_points[:10]


def _detect_common_patterns(root: Path, modules: list[ModuleInfo]) -> list[str]:
    """Detect recurring patterns Claude should follow."""
    patterns = []

    decorator_counts: dict[str, int] = {}
    for py_file in root.rglob("*.py"):
        if any(skip in py_file.parts for skip in SKIP_DIRS):
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            for match in re.findall(r"@(\w+(?:\.\w+)*)", content):
                decorator_counts[match] = decorator_counts.get(match, 0) + 1
        except Exception:
            continue

    common_decorators = [(d, c) for d, c in decorator_counts.items() if c >= 3]
    if common_decorators:
        top = sorted(common_decorators, key=lambda x: -x[1])[:5]
        patterns.append(f"Common decorators: {', '.join(f'@{d} ({c}x)' for d, c in top)}")

    # Detect test patterns
    test_modules = [m for m in modules if "test" in m.path.lower()]
    if test_modules:
        patterns.append(f"Tests: {len(test_modules)} test files, mirror src/ structure")

    # Detect dataclass usage
    dc_count = sum(1 for m in modules if any("dataclass" in i for i in m.imports_from))
    if dc_count >= 2:
        patterns.append(f"Dataclasses used in {dc_count} modules")

    return patterns


def _find_skip_candidates(root: Path, modules: list[ModuleInfo]) -> list[str]:
    """Find files Claude should never bother reading."""
    skip = []
    for mod in modules:
        if mod.line_count > 500:
            skip.append(f"{mod.path} ({mod.line_count} lines, {mod.complexity})")
        if any(kw in mod.path.lower() for kw in ("generated", "migration", "vendor", "lock")):
            skip.append(f"{mod.path} (auto-generated/vendored)")

    for f in root.rglob("*"):
        if f.is_file() and f.suffix in {".json", ".lock", ".svg", ".min.js"}:
            if any(skip_dir in f.parts for skip_dir in SKIP_DIRS):
                continue
            try:
                size = f.stat().st_size
                if size > 50_000:
                    skip.append(f"{f.relative_to(root)} ({size // 1024}KB, skip)")
            except Exception:
                continue

    return skip[:20]


def _build_dependency_flow(layers: dict[str, list[ModuleInfo]]) -> list[str]:
    """Build simplified dependency flow arrows."""
    flows = []
    layer_order = ["api", "cli", "services", "generators", "session", "analysis", "models", "data", "config"]
    present = [layer for layer in layer_order if layer in layers]
    if len(present) >= 2:
        flows.append(" -> ".join(present))
    return flows


def render_architecture_md(arch: ArchitectureMap) -> str:
    """Render the architecture map as CLAUDE.md content."""
    lines = []

    if arch.dependency_flow:
        lines.append("## Architecture Flow")
        for flow in arch.dependency_flow:
            lines.append(f"  {flow}")
        lines.append("")

    for layer_name, modules in arch.layers.items():
        if layer_name == "tests":
            continue
        lines.append(f"### {layer_name.title()} Layer")
        for mod in sorted(modules, key=lambda m: m.path):
            api_str = f" -- exports: {', '.join(mod.public_api[:5])}" if mod.public_api else ""
            lines.append(f"- `{mod.path}`: {mod.purpose}{api_str}")
        lines.append("")

    if arch.entry_points:
        lines.append("## Entry Points")
        for ep in arch.entry_points:
            lines.append(f"- `{ep}`")
        lines.append("")

    if arch.common_patterns:
        lines.append("## Patterns to Follow")
        for p in arch.common_patterns:
            lines.append(f"- {p}")
        lines.append("")

    if arch.skip_files:
        lines.append("## Skip These Files (don't read unless specifically asked)")
        for sf in arch.skip_files:
            lines.append(f"- {sf}")
        lines.append("")

    return "\n".join(lines)


def generate_anti_exploration(arch: ArchitectureMap) -> str:
    """Generate directives that prevent wasteful exploration."""
    lines = ["## What NOT To Do (each violation wastes ~1,500 tokens)\n"]

    if arch.skip_files:
        lines.append("### Don't Read These Files")
        for f in arch.skip_files[:10]:
            lines.append(f"- {f}")
        lines.append("")

    lines.append("### Don't Explore (use the map above instead)")
    lines.append("- Don't `ls` or `find` to discover project structure -- it's documented above")
    lines.append("- Don't read __init__.py files -- they're usually empty or just imports")
    lines.append("- Don't read test files to understand implementation -- read the source")
    lines.append("- Don't grep for imports -- the dependency flow is documented above")
    lines.append("")

    lines.append("### Don't Waste Output Tokens")
    lines.append("- Don't summarize files after reading them")
    lines.append("- Don't explain code changes unless asked")
    lines.append("- Don't list what you're about to do -- just do it")
    lines.append("- Don't show full file contents -- show only the changed lines")

    return "\n".join(lines)
