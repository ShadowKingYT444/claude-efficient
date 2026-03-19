# tests/test_init.py
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from claude_efficient.cli.init import init


def test_init_creates_core_files(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'")

    mock_backend = MagicMock()
    mock_backend.name = "gemini"
    mock_backend._build_payload.return_value = ""
    mock_backend.summarize.return_value = "# Test\n## Output format\nCode only."

    runner = CliRunner()
    with patch("claude_efficient.cli.init.detect_backend", return_value=mock_backend), \
         patch("claude_efficient.cli.init._check_claude_mem"):
        result = runner.invoke(init, ["--root", str(tmp_path), "--no-import-tree"])

    assert result.exit_code == 0
    assert (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / ".claudeignore").exists()
    assert (tmp_path / ".claude" / "settings.json").exists()
    # TASKS.md should NOT be created — claude-mem handles this
    assert not (tmp_path / "TASKS.md").exists()


def test_init_does_not_overwrite_precompact_hooks(tmp_path):
    """Existing .claude/settings.json hooks should be preserved."""
    import json
    (tmp_path / ".claude").mkdir()
    existing = {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "echo hi"}]}]}}
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps(existing))
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'")

    mock_backend = MagicMock()
    mock_backend.name = "gemini"
    mock_backend._build_payload.return_value = ""
    mock_backend.summarize.return_value = "# Test"

    runner = CliRunner()
    with patch("claude_efficient.cli.init.detect_backend", return_value=mock_backend), \
         patch("claude_efficient.cli.init._check_claude_mem"):
        runner.invoke(init, ["--root", str(tmp_path), "--no-import-tree"])

    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert "UserPromptSubmit" in settings["hooks"]   # original hook preserved
    assert "PreCompact" in settings["hooks"]          # new hook added
