# src/claude_efficient/session/mcp_config.py
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ALWAYS_KEEP: frozenset[str] = frozenset({"claude_mem", "memory", "filesystem"})

# Keywords that indicate a server is relevant to a task
MCP_RELEVANCE_MAP: dict[str, list[str]] = {
    "gmail": ["email", "draft", "reply", "inbox", "send", "mail"],
    "google_calendar": ["calendar", "meeting", "schedule", "event", "appointment"],
    "google_drive": ["document", "drive", "gdoc", "sheet", "slides"],
    "github": ["pr", "pull request", "commit", "issue", "repo", "branch", "git"],
    "slack": ["slack", "channel", "dm", "message"],
    "asana": ["task", "asana", "sprint", "ticket", "project management"],
}


@dataclass
class McpSessionPlan:
    has_experimental_flag: bool
    active_servers: list[str]
    deferred_servers: list[str]
    tokens_overhead: int
    advice: list[str] = field(default_factory=list)


class McpConfigAdvisor:
    """
    Advises on MCP configuration for a session.
    Never removes servers mid-session. Only recommends or generates pre-session config.
    """

    TOKENS_PER_SERVER = 1_200

    def plan_session(
        self,
        task_prompt: str,
        all_servers: list[str],
        root: Path = Path("."),
    ) -> McpSessionPlan:
        has_flag = os.environ.get("ENABLE_EXPERIMENTAL_MCP_CLI", "").lower() in ("1", "true")
        always_keep = self._load_always_keep(root)
        lowered = task_prompt.lower()

        if has_flag:
            # With deferred loading, all servers are "active" but schemas load on demand.
            # No overhead concern — report everything as active.
            return McpSessionPlan(
                has_experimental_flag=True,
                active_servers=all_servers,
                deferred_servers=[],
                tokens_overhead=0,
                advice=[
                    "ENABLE_EXPERIMENTAL_MCP_CLI=true detected — schemas load on demand.",
                    "No MCP token overhead at session start.",
                ],
            )

        # Without the flag: identify which servers are actually needed
        active, deferred = [], []
        for server in all_servers:
            if server in always_keep:
                active.append(server)
                continue
            keywords = MCP_RELEVANCE_MAP.get(server, [])
            if any(kw in lowered for kw in keywords):
                active.append(server)
            else:
                deferred.append(server)

        overhead = len(all_servers) * self.TOKENS_PER_SERVER  # current overhead
        savings = len(deferred) * self.TOKENS_PER_SERVER

        advice = []
        if deferred:
            advice.append(
                f"{len(deferred)} server(s) appear unused for this task "
                f"(~{savings:,} tokens): {deferred}"
            )
            advice.append(
                "To reduce overhead: set ENABLE_EXPERIMENTAL_MCP_CLI=true (preferred), "
                "or run `ce mcp-session-config` to generate a task-scoped .mcp.json "
                "BEFORE starting the session."
            )
        if not has_flag:
            advice.append(
                "Recommended: export ENABLE_EXPERIMENTAL_MCP_CLI=true in your shell profile."
            )

        return McpSessionPlan(
            has_experimental_flag=False,
            active_servers=active,
            deferred_servers=deferred,
            tokens_overhead=overhead,
            advice=advice,
        )

    def write_session_mcp_json(
        self,
        root: Path,
        active_servers: list[str],
        source_config: Path | None = None,
    ) -> Path:
        """
        Write a .mcp.json for the session that includes only active_servers.
        Must be called BEFORE the session starts — never during.
        Source config is read from ~/.claude/claude_desktop_config.json if not specified.
        """
        if source_config is None:
            source_config = Path.home() / ".claude" / "claude_desktop_config.json"

        all_server_defs: dict = {}
        if source_config.exists():
            try:
                data = json.loads(source_config.read_text())
                all_server_defs = data.get("mcpServers", {})
            except Exception:
                pass

        session_servers = {
            name: cfg
            for name, cfg in all_server_defs.items()
            if name in active_servers
        }

        out = root / ".mcp.json"
        out.write_text(json.dumps({"mcpServers": session_servers}, indent=2))
        return out

    def _load_always_keep(self, root: Path) -> frozenset[str]:
        for candidate in (
            root / ".claude-efficient.toml",
            Path(__file__).parent.parent / "config" / "defaults.toml",
        ):
            if candidate.exists():
                try:
                    import tomllib
                    with open(candidate, "rb") as f:
                        return frozenset(
                            tomllib.load(f).get("mcp", {}).get("always_keep", DEFAULT_ALWAYS_KEEP)
                        )
                except Exception:
                    pass
        return DEFAULT_ALWAYS_KEEP
