# src/claude_efficient/analysis/cache_health.py
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CacheRisk:
    severity: str          # "critical" | "warning" | "info"
    code: str              # machine-readable key
    message: str
    fix: str


@dataclass
class CacheHealthReport:
    risks: list[CacheRisk] = field(default_factory=list)

    @property
    def has_critical(self) -> bool:
        return any(r.severity == "critical" for r in self.risks)

    @property
    def is_healthy(self) -> bool:
        return not self.risks


class CacheHealthMonitor:
    """
    Static pre-session checks. Run before launching claude to catch
    configuration mistakes that invalidate prompt caching.
    """

    # Known session token overhead per unflagged MCP server schema
    TOKENS_PER_MCP_SERVER = 1_200

    def check_all(self, root: Path = Path(".")) -> CacheHealthReport:
        report = CacheHealthReport()
        for check in (
            self._check_experimental_mcp_flag,
            self._check_model_not_in_env,
            self._check_claude_md_size,
            self._check_always_keep_config,
        ):
            risk = check(root)
            if risk:
                report.risks.append(risk)
        return report

    # ------------------------------------------------------------------ checks

    def _check_experimental_mcp_flag(self, root: Path) -> CacheRisk | None:
        if os.environ.get("ENABLE_EXPERIMENTAL_MCP_CLI", "").lower() in ("1", "true"):
            return None  # flag is set — MCP schemas load on-demand

        # Count MCP servers in Claude Code config
        mcp_count = self._count_mcp_servers(root)
        if mcp_count == 0:
            return None

        wasted = mcp_count * self.TOKENS_PER_MCP_SERVER
        return CacheRisk(
            severity="critical",
            code="missing_experimental_mcp_flag",
            message=(
                f"ENABLE_EXPERIMENTAL_MCP_CLI is not set. "
                f"{mcp_count} MCP server schema(s) load upfront "
                f"(~{wasted:,} tokens before you type a word)."
            ),
            fix=(
                "Add to your shell profile:\n"
                "  export ENABLE_EXPERIMENTAL_MCP_CLI=true\n"
                "Or prefix the session:\n"
                "  ENABLE_EXPERIMENTAL_MCP_CLI=true ce run 'your task'"
            ),
        )

    def _check_model_not_in_env(self, root: Path) -> CacheRisk | None:
        """Warn if ANTHROPIC_MODEL is set — it can cause implicit mid-session routing."""
        model_env = os.environ.get("ANTHROPIC_MODEL", "")
        if not model_env:
            return None
        return CacheRisk(
            severity="warning",
            code="model_env_override",
            message=(
                f"ANTHROPIC_MODEL={model_env!r} is set in the environment. "
                "ce's model router will be bypassed — model stays fixed at session start."
            ),
            fix="This is fine as long as you intended this model for the full session.",
        )

    def _check_claude_md_size(self, root: Path) -> CacheRisk | None:
        claude_md = root / "CLAUDE.md"
        if not claude_md.exists():
            return CacheRisk(
                severity="warning",
                code="missing_claude_md",
                message="No CLAUDE.md found. Claude will navigate files at token cost.",
                fix="Run `ce init` to generate CLAUDE.md.",
            )
        size = len(claude_md.read_bytes())
        if size > 4_000:
            return CacheRisk(
                severity="warning",
                code="claude_md_too_large",
                message=(
                    f"CLAUDE.md is {size:,} bytes. Files over ~4KB degrade "
                    "instruction-following — Claude starts ignoring later rules."
                ),
                fix=(
                    "Run `ce init --reimport` to split into root + @import subdirectory files. "
                    "Target: root under 2KB, subdirs under 600 bytes each."
                ),
            )
        return None

    def _check_always_keep_config(self, root: Path) -> CacheRisk | None:
        config_file = root / ".claude-efficient.toml"
        if not config_file.exists():
            return None
        try:
            import tomllib
            with open(config_file, "rb") as f:
                data = tomllib.load(f)
            always_keep = set(data.get("mcp", {}).get("always_keep", []))
            missing = {"claude_mem", "memory"} - always_keep
            if missing:
                return CacheRisk(
                    severity="critical",
                    code="claude_mem_not_protected",
                    message=(
                        f"{missing} are not in always_keep. "
                        "If auto_prune runs, claude-mem hooks will be disabled — "
                        "that session produces zero memory."
                    ),
                    fix=(
                        'Add to .claude-efficient.toml:\n'
                        '[mcp]\nalways_keep = ["claude_mem", "memory", "filesystem"]'
                    ),
                )
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------ helpers

    def _count_mcp_servers(self, root: Path) -> int:
        """
        Count MCP servers from Claude Code's config.
        Checks project .mcp.json first, then falls back to global config.
        """
        # Project-level override
        project_mcp = root / ".mcp.json"
        if project_mcp.exists():
            try:
                import json
                data = json.loads(project_mcp.read_text())
                return len(data.get("mcpServers", {}))
            except Exception:
                pass

        # Global Claude Code config
        global_config = Path.home() / ".claude" / "claude_desktop_config.json"
        if global_config.exists():
            try:
                import json
                data = json.loads(global_config.read_text())
                return len(data.get("mcpServers", {}))
            except Exception:
                pass

        return 0