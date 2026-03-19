from dataclasses import dataclass
from pathlib import Path

@dataclass
class PruneResult:
    keep: list[str]
    pruned: list[str]
    tokens_saved: int

MCP_TASK_MAP = {
    "github": ["git", "github", "pr", "issue", "repo", "commit", "push", "pull", "branch"],
    "slack": ["slack", "message", "channel", "ping"],
    "jira": ["jira", "ticket", "issue", "board", "sprint", "epic"],
    "asana": ["asana", "task", "project"],
    "gmail": ["email", "gmail", "inbox", "send"],
}

OVERHEAD_PER_SERVER_TOKENS = 1000

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
