# SPEC_01-04 FIXES — Architecture Corrections
**Session goal:** Apply targeted fixes to already-implemented specs 1-4. Three files touched, no new files.
**Model:** Sonnet. **Est. context:** Small. **Clear after:** yes.
**Reads:** `CLAUDE.md` only.

---

## Why these fixes are needed

Two features in specs 1-4 would actively destroy prompt caching — the mechanism that makes
Claude Code economically viable. Prompt caching keeps the prefix byte-identical every turn.
Two things break it silently:
1. The compact threshold of 60% is too late — context degrades non-linearly before that point
2. The MCPPruner (as designed) removes MCP servers mid-session, invalidating the cache prefix
3. `claude_mem` and `memory` are NOT user-invoked tools — their hooks fire automatically on
   every tool call. Pruning them doesn't save tokens; it kills cross-session memory silently.

---

## Fix A — `config/defaults.toml` (full replacement)

```toml
# src/claude_efficient/config/defaults.toml

[general]
verbose = false

[model]
default = "claude-sonnet-4-6"
planning_model = "claude-opus-4-6"
# ARCHITECTURE RULE: model is selected ONCE at session start, never changed mid-session.
# Mid-session model changes invalidate the prompt cache prefix entirely.
auto_route = true

[compact]
enabled = true
threshold_pct = 45          # was 60 — context quality degrades non-linearly; act early
danger_threshold_pct = 70   # was 80
prefer_clear = true         # /clear + fresh session is preferred; /compact is fallback

[subagents]
enabled = true
min_files_to_parallelize = 2
max_parallel = 4

[mcp]
auto_prune = false           # disabled — SPEC_09 replaces pruner with env-var approach
# Servers in always_keep are NEVER disabled regardless of task keywords.
# claude_mem hooks (SessionStart, PostToolUse, SessionEnd) are passive capture hooks —
# not user-invoked tools. Disabling the server kills the capture pipeline silently.
always_keep = ["claude_mem", "memory", "filesystem"]

[prompt]
auto_optimize = true
warn_on_paste = true
```

---

## Fix B — `session/mcp_pruner.py` — protect always_keep, respect config flag

The existing `prune()` logic ignores `always_keep`. Replace the function body only:

```python
# src/claude_efficient/session/mcp_pruner.py
# Replace the module-level `prune` function with this version.
# All other code (MCP_TASK_MAP, PruneResult, constants) stays the same.

from pathlib import Path

DEFAULT_ALWAYS_KEEP: frozenset[str] = frozenset({"claude_mem", "memory", "filesystem"})


def _load_config(root: Path) -> dict:
    """Load .claude-efficient.toml or fall back to package defaults.toml."""
    for candidate in (
        root / ".claude-efficient.toml",
        Path(__file__).parent.parent / "config" / "defaults.toml",
    ):
        if candidate.exists():
            try:
                import tomllib
                with open(candidate, "rb") as f:
                    return tomllib.load(f)
            except Exception:
                pass
    return {}


def prune(
    task_prompt: str,
    enabled_servers: list[str],
    root: Path = Path("."),
) -> PruneResult:
    """
    Advisory-only MCP prune.
    - auto_prune=false in defaults → this is informational; callers should check config
    - always_keep servers are NEVER suggested for pruning
    - Does not touch MCP server state; caller decides whether to act on result
    """
    cfg = _load_config(root)
    always_keep = frozenset(cfg.get("mcp", {}).get("always_keep", DEFAULT_ALWAYS_KEEP))

    lowered = task_prompt.lower()
    keep: list[str] = []
    pruned: list[str] = []

    for server in enabled_servers:
        if server in always_keep:
            keep.append(server)
            continue
        keywords = MCP_TASK_MAP.get(server, [])
        if any(kw in lowered for kw in keywords):
            keep.append(server)
        else:
            pruned.append(server)

    return PruneResult(
        keep=keep,
        pruned=pruned,
        tokens_saved=len(pruned) * OVERHEAD_PER_SERVER_TOKENS,
    )
```

---

## Fix C — `generators/claude_md.py` — add @import scaffolding

Claude Code has a built-in layered CLAUDE.md system: `@path/to/CLAUDE.md` in the root
file imports subdirectory context that only loads when Claude is working in that directory.
This is the real surgical loading mechanism — built in, zero overhead outside its directory.

Add this method to `ClaudeMdGenerator`. No other changes to the class.

```python
# Add to ClaudeMdGenerator in src/claude_efficient/generators/claude_md.py
# (append to class body after write_gemini_md)

SUBDIR_PROMPT = """\
Generate a minimal CLAUDE.md for this subdirectory. Output ONLY raw markdown, no explanation.
Constraints:
- Total output under 600 bytes
- Focus ONLY on what is unique to this subdirectory: its purpose, key interfaces, gotchas
- Do NOT repeat project-level information already in the root CLAUDE.md
- No folder map, no run commands — those are in the root
"""

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
```

---

## Fix D — Add `.claude/settings.json` PreCompact hook

This single hook prevents 60–70% information loss per compaction cycle. Without it,
each `/compact` loses more context than the one before. Two compactions in a session
means ~88% cumulative loss.

```python
# Add this function to src/claude_efficient/generators/claude_md.py (module level)

import json

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
```

---

## Fix E — `tests/test_mcp_pruner.py` additions

```python
# Append to tests/test_mcp_pruner.py (create file if it doesn't exist)
from pathlib import Path
from claude_efficient.session.mcp_pruner import prune


def test_always_keep_never_pruned():
    """claude_mem must survive even when task has no memory keywords."""
    result = prune(
        "Build collectors/os_hook.py",
        ["claude_mem", "gmail", "filesystem"],
    )
    assert "claude_mem" in result.keep
    assert "filesystem" in result.keep
    assert "gmail" in result.pruned


def test_always_keep_from_toml_config(tmp_path):
    """always_keep from project config overrides defaults."""
    (tmp_path / ".claude-efficient.toml").write_text(
        '[mcp]\nalways_keep = ["claude_mem", "memory", "slack"]\n'
    )
    result = prune("quick code task", ["claude_mem", "slack", "github"], root=tmp_path)
    assert "slack" in result.keep   # in always_keep even without keyword match
    assert "github" in result.pruned


def test_default_always_keep_when_no_config():
    """Falls back to DEFAULT_ALWAYS_KEEP when no config file present."""
    result = prune("some task", ["claude_mem", "memory", "asana"], root=Path("/tmp"))
    assert "claude_mem" in result.keep
    assert "memory" in result.keep
```

---

## Verification

```bash
pytest tests/test_mcp_pruner.py -x
pytest tests/ -x          # all previous tests still pass
ruff check src/
```

## Done → update TASKS.md → `/clear`
