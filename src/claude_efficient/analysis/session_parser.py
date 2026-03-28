"""Parse Claude Code session data after an interactive session completes.

Claude Code stores session data in ~/.claude/projects/<hash>/sessions/.
After a session ends, we can read the conversation JSON to extract
actual token usage that wasn't available during the session.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SessionTokens:
    total_input: int = 0
    total_output: int = 0
    total_cache_read: int = 0
    turn_count: int = 0
    tools_used: dict[str, int] = field(default_factory=dict)


def parse_last_session(project_root: Path) -> SessionTokens | None:
    """Find and parse the most recent Claude Code session for this project."""
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        return None

    latest_session = None
    latest_mtime = 0.0

    try:
        for project_dir in claude_dir.iterdir():
            if not project_dir.is_dir():
                continue
            # Check both "sessions" and direct JSONL files
            for pattern in ("sessions/*.jsonl", "*.jsonl"):
                for session_file in project_dir.glob(pattern):
                    try:
                        mtime = session_file.stat().st_mtime
                        if mtime > latest_mtime:
                            latest_mtime = mtime
                            latest_session = session_file
                    except OSError:
                        continue
    except (OSError, PermissionError):
        return None

    if latest_session is None:
        return None

    return _parse_session_file(latest_session)


def _parse_session_file(path: Path) -> SessionTokens:
    """Parse a Claude Code session JSONL file for token usage."""
    result = SessionTokens()

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return result

    for line in content.splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue

        # Extract usage from various possible locations
        usage = data.get("usage") or {}
        if not isinstance(usage, dict):
            usage = {}

        result.total_input += usage.get("input_tokens", 0)
        result.total_output += usage.get("output_tokens", 0)
        result.total_cache_read += usage.get("cache_read_input_tokens", 0)

        if data.get("role") == "assistant":
            result.turn_count += 1

        # Track tool usage from content blocks
        content_blocks = data.get("content", [])
        if isinstance(content_blocks, list):
            for block in content_blocks:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_name = block.get("name", "unknown")
                    result.tools_used[tool_name] = result.tools_used.get(tool_name, 0) + 1

    return result
