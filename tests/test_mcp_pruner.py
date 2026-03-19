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
