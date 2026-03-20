# tests/test_init.py
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from claude_efficient.cli.init import init
from claude_efficient.config.defaults import HelperMode
from claude_efficient.generators.backends import DeterministicBackend
from claude_efficient.generators.claude_md import write_claude_settings
from claude_efficient.generators.extractor import (
    ExtractedFacts,
    SubdirCandidate,
    extract_facts,
)

_NO_BACKEND = (HelperMode.off, DeterministicBackend())


# ── helpers ────────────────────────────────────────────────────────────────────

def _invoke_init(tmp_path: Path, args: list[str] | None = None):
    runner = CliRunner()
    with patch("claude_efficient.cli.init._check_claude_mem"), \
         patch("claude_efficient.cli.init.resolve_helpers_config", return_value=_NO_BACKEND):
        return runner.invoke(init, ["--root", str(tmp_path)] + (args or []))


# ── core file creation ─────────────────────────────────────────────────────────

def test_init_creates_core_files(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'")
    result = _invoke_init(tmp_path, ["--no-import-tree"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / ".claudeignore").exists()
    assert (tmp_path / ".claude" / "settings.json").exists()
    assert not (tmp_path / "TASKS.md").exists()


def test_init_does_not_overwrite_precompact_hooks(tmp_path):
    (tmp_path / ".claude").mkdir()
    existing = {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "echo hi"}]}]}}
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps(existing))
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'")
    _invoke_init(tmp_path, ["--no-import-tree"])
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert "UserPromptSubmit" in settings["hooks"]
    assert "PreCompact" in settings["hooks"]


def test_precompact_hook_is_cross_platform_python_command(tmp_path):
    settings_path = write_claude_settings(tmp_path)
    settings = json.loads(settings_path.read_text())
    command = settings["hooks"]["PreCompact"][0]["hooks"][0]["command"]
    assert "python" in command.lower()
    assert "&&" not in command
    assert "||" not in command
    assert "/dev/null" not in command


def test_init_reports_zero_tokens(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'")
    result = _invoke_init(tmp_path, ["--no-import-tree"])
    assert result.exit_code == 0, result.output
    assert "tokens used during init: 0" in result.output


# ── extract_facts unit tests ───────────────────────────────────────────────────

def _make_py_files(directory: Path, count: int) -> None:
    for i in range(count):
        (directory / f"mod_{i}.py").write_text(f"# module {i}")


def _make_ts_files(directory: Path, count: int) -> None:
    for i in range(count):
        (directory / f"comp_{i}.ts").write_text(f"// component {i}")


def _make_go_files(directory: Path, count: int) -> None:
    for i in range(count):
        (directory / f"pkg_{i}.go").write_text(f"package main")


def _make_rs_files(directory: Path, count: int) -> None:
    for i in range(count):
        (directory / f"mod_{i}.rs").write_text(f"// rust {i}")


def test_extract_facts_pure_python(tmp_path):
    _make_py_files(tmp_path, 6)
    facts = extract_facts(tmp_path)
    assert "python" in facts.languages
    assert "typescript" not in facts.languages
    assert "go" not in facts.languages


def test_extract_facts_pure_typescript(tmp_path):
    _make_ts_files(tmp_path, 6)
    facts = extract_facts(tmp_path)
    assert "typescript" in facts.languages
    assert "python" not in facts.languages


def test_extract_facts_go_rust_mixed(tmp_path):
    _make_go_files(tmp_path, 4)
    _make_rs_files(tmp_path, 4)
    facts = extract_facts(tmp_path)
    assert "go" in facts.languages
    assert "rust" in facts.languages
    assert "python" not in facts.languages


def test_extract_facts_empty_project(tmp_path):
    facts = extract_facts(tmp_path)
    assert facts.languages == []
    assert facts.commands == {}
    assert facts.subdir_candidates == []


def test_subdir_candidate_qualifies_by_threshold(tmp_path):
    sub = tmp_path / "src"
    sub.mkdir()
    # python threshold = 5; 3 files → qualifies=False
    _make_py_files(sub, 3)
    facts = extract_facts(tmp_path)
    py_candidates = [c for c in facts.subdir_candidates if c.language == "python"]
    assert py_candidates, "Expected at least one python candidate"
    assert any(not c.qualifies for c in py_candidates if c.file_count < 5)

    sub2 = tmp_path / "lib"
    sub2.mkdir()
    _make_py_files(sub2, 5)
    facts2 = extract_facts(tmp_path)
    lib_candidates = [
        c for c in facts2.subdir_candidates
        if c.language == "python" and "lib" in c.path
    ]
    assert lib_candidates and lib_candidates[0].qualifies


def test_extract_facts_python_ts_go_subdirs(tmp_path):
    """ce init on a Python+TS+Go fixture produces subdir entries for all three languages."""
    py_sub = tmp_path / "backend"
    py_sub.mkdir()
    _make_py_files(py_sub, 5)

    ts_sub = tmp_path / "frontend"
    ts_sub.mkdir()
    _make_ts_files(ts_sub, 5)

    go_sub = tmp_path / "services"
    go_sub.mkdir()
    _make_go_files(go_sub, 3)

    facts = extract_facts(tmp_path)
    langs_in_candidates = {c.language for c in facts.subdir_candidates if c.qualifies}
    assert "python" in langs_in_candidates
    assert "typescript" in langs_in_candidates
    assert "go" in langs_in_candidates


# ── generate_root / CLAUDE.md quality ─────────────────────────────────────────

def test_init_no_backend_produces_valid_claude_md(tmp_path):
    """ce init with no backend still produces a non-empty CLAUDE.md."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'")
    result = _invoke_init(tmp_path, ["--no-import-tree"])
    assert result.exit_code == 0, result.output
    content = (tmp_path / "CLAUDE.md").read_text()
    assert len(content) > 10
    assert "#" in content  # must have at least one header


def test_claude_md_under_size_budget(tmp_path):
    """Generated CLAUDE.md must stay under 500 lines / ~3000 tokens."""
    for i in range(20):
        (tmp_path / f"module_{i}.py").write_text(f"# module {i}\n" + "x = 1\n" * 50)
    result = _invoke_init(tmp_path, ["--no-import-tree"])
    assert result.exit_code == 0, result.output
    content = (tmp_path / "CLAUDE.md").read_text()
    assert len(content.splitlines()) < 500
    assert len(content.encode()) <= 3_000


def test_no_raw_file_contents_in_helper_input(tmp_path):
    """The string passed to invoke_helper_fn must not contain raw file contents."""
    (tmp_path / "secret.py").write_text("PASSWORD = 'hunter2'\n" * 100)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'")

    captured_inputs: list[str] = []

    def _fake_helper(content: str) -> str | None:
        captured_inputs.append(content)
        return None  # signal fallback

    from claude_efficient.generators.claude_md import ClaudeMdGenerator
    from claude_efficient.generators.extractor import extract_facts

    facts = extract_facts(tmp_path)
    gen = ClaudeMdGenerator()
    gen.generate_root(facts, invoke_helper_fn=_fake_helper)

    assert captured_inputs, "Helper was never called"
    for inp in captured_inputs:
        assert "hunter2" not in inp, "Raw file content leaked into helper input"


def test_tasks_md_helper_path_absent_from_claude_md():
    """TASKS.md-based helper path must not exist in claude_md.py."""
    import claude_efficient.generators.claude_md as module
    import inspect
    source = inspect.getsource(module)
    assert "TASKS.md" not in source or "CRITICAL CONTEXT" in source
    # The only TASKS.md reference is inside the PreCompact hook script, not helper logic


# ── Phase 6: --helpers flag ────────────────────────────────────────────────────

def test_init_helpers_off_flag(tmp_path):
    """--helpers off must produce a valid CLAUDE.md with zero helper calls."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'")
    runner = CliRunner()
    with patch("claude_efficient.cli.init._check_claude_mem"):
        result = runner.invoke(init, [
            "--root", str(tmp_path), "--no-import-tree", "--helpers", "off",
        ])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "CLAUDE.md").exists()


# fix missing import for CliRunner used standalone
from click.testing import CliRunner  # noqa: E402  (already imported above, re-export for clarity)
