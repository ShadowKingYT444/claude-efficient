from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4


@dataclass
class PruneResult:
    keep: list[str]
    pruned: list[str]
    tokens_saved: int


@dataclass
class AutoPruneSession:
    result: PruneResult
    auto_prune_enabled: bool
    applied: bool
    reason: str = ""
    output_path: Path | None = None
    backup_path: Path | None = None
    active_servers: list[str] = field(default_factory=list)


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


def _load_mcp_settings(root: Path) -> dict:
    return _load_config(root).get("mcp", {})


def is_auto_prune_enabled(root: Path = Path(".")) -> bool:
    value = _load_mcp_settings(root).get("auto_prune", False)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _read_server_definitions(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        servers = data.get("mcpServers", {})
        return servers if isinstance(servers, dict) else {}
    except Exception:
        return {}


def _load_server_definitions(root: Path, source_config: Path | None) -> dict[str, dict]:
    candidates = [source_config] if source_config is not None else []
    candidates.extend(
        [root / ".mcp.json", Path.home() / ".claude" / "claude_desktop_config.json"]
    )
    for candidate in candidates:
        if candidate is None:
            continue
        defs = _read_server_definitions(candidate)
        if defs:
            return defs
    return {}


def discover_enabled_servers(root: Path = Path(".")) -> list[str]:
    mcp_cfg = _load_mcp_settings(root)
    configured = mcp_cfg.get("enabled_servers", [])
    if isinstance(configured, list) and configured:
        return [name for name in configured if isinstance(name, str)]

    for candidate in (
        root / ".mcp.json",
        Path.home() / ".claude" / "claude_desktop_config.json",
    ):
        servers = _read_server_definitions(candidate)
        if servers:
            return list(servers.keys())
    return []


def prune(
    task_prompt: str,
    enabled_servers: list[str],
    root: Path = Path("."),
) -> PruneResult:
    """
    Compute which MCP servers should stay active for the task.
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


@contextmanager
def auto_pruned_session_config(
    task_prompt: str,
    enabled_servers: list[str] | None = None,
    *,
    root: Path = Path("."),
    source_config: Path | None = None,
):
    """
    Write a task-scoped .mcp.json before session start and restore original state.
    No-op unless [mcp].auto_prune is enabled.
    """
    root = root.resolve()
    known_servers = list(enabled_servers or discover_enabled_servers(root))
    prune_result = prune(task_prompt, known_servers, root=root)
    auto_enabled = is_auto_prune_enabled(root)

    if not auto_enabled:
        yield AutoPruneSession(
            result=prune_result,
            auto_prune_enabled=False,
            applied=False,
            reason="auto_prune disabled in config",
        )
        return

    if not known_servers:
        yield AutoPruneSession(
            result=prune_result,
            auto_prune_enabled=True,
            applied=False,
            reason="no MCP servers discovered",
        )
        return

    server_defs = _load_server_definitions(root, source_config)
    if not server_defs:
        yield AutoPruneSession(
            result=prune_result,
            auto_prune_enabled=True,
            applied=False,
            reason="no MCP server definitions found in project/global config",
        )
        return

    active_servers = [name for name in prune_result.keep if name in server_defs]
    if not active_servers:
        yield AutoPruneSession(
            result=prune_result,
            auto_prune_enabled=True,
            applied=False,
            reason="none of the selected MCP servers had definitions",
        )
        return

    output_path = root / ".mcp.json"
    backup_path: Path | None = None
    had_existing = output_path.exists()
    if had_existing:
        backup_path = root / f".mcp.json.ce-backup-{uuid4().hex}"
        backup_path.write_bytes(output_path.read_bytes())

    scoped_config = {
        "mcpServers": {name: server_defs[name] for name in active_servers},
    }
    output_path.write_text(json.dumps(scoped_config, indent=2), encoding="utf-8")

    session = AutoPruneSession(
        result=prune_result,
        auto_prune_enabled=True,
        applied=True,
        reason="task-scoped .mcp.json applied",
        output_path=output_path,
        backup_path=backup_path,
        active_servers=active_servers,
    )

    try:
        yield session
    finally:
        try:
            if had_existing and backup_path and backup_path.exists():
                output_path.write_bytes(backup_path.read_bytes())
                backup_path.unlink(missing_ok=True)
            elif output_path.exists():
                output_path.unlink(missing_ok=True)
        except Exception:
            # Never fail the coding session if rollback of session config has issues.
            pass
