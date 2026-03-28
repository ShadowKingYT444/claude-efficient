import json
from pathlib import Path

from claude_efficient.session.mcp_pruner import (
    auto_pruned_session_config,
    discover_enabled_servers,
    is_auto_prune_enabled,
    prune,
)

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


def test_auto_prune_enabled_by_default_from_package_defaults(tmp_path):
    assert is_auto_prune_enabled(tmp_path) is True


def test_discover_enabled_servers_from_project_mcp_json(tmp_path):
    (tmp_path / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "claude_mem": {"command": "mem"},
                    "github": {"command": "gh"},
                }
            }
        )
    )
    servers = discover_enabled_servers(tmp_path)
    assert "claude_mem" in servers
    assert "github" in servers


def test_auto_pruned_session_config_writes_and_restores(tmp_path):
    (tmp_path / ".claude-efficient.toml").write_text(
        '[mcp]\nauto_prune = true\nalways_keep = ["claude_mem", "memory", "filesystem"]\n'
    )
    source = tmp_path / "source-mcp.json"
    source.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "claude_mem": {"command": "mem"},
                    "github": {"command": "gh"},
                    "gmail": {"command": "gmail"},
                }
            }
        )
    )
    original = {"mcpServers": {"legacy": {"command": "legacy"}}}
    existing = tmp_path / ".mcp.json"
    existing.write_text(json.dumps(original))

    with auto_pruned_session_config(
        "open github issue and sync",
        ["claude_mem", "github", "gmail"],
        root=tmp_path,
        source_config=source,
    ) as session:
        assert session.applied is True
        assert "claude_mem" in session.active_servers
        assert "github" in session.active_servers
        assert "gmail" not in session.active_servers
        scoped = json.loads(existing.read_text())
        assert set(scoped["mcpServers"].keys()) == {"claude_mem", "github"}

    restored = json.loads(existing.read_text())
    assert restored == original


def test_auto_pruned_session_config_skips_when_disabled(tmp_path):
    (tmp_path / ".claude-efficient.toml").write_text("[mcp]\nauto_prune = false\n")
    source = tmp_path / "source-mcp.json"
    source.write_text(json.dumps({"mcpServers": {"claude_mem": {"command": "mem"}}}))

    with auto_pruned_session_config(
        "code task",
        ["claude_mem"],
        root=tmp_path,
        source_config=source,
    ) as session:
        assert session.applied is False
        assert session.auto_prune_enabled is False
        assert "disabled" in session.reason
    assert not (tmp_path / ".mcp.json").exists()
