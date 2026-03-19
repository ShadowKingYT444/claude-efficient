from claude_efficient.generators.claudeignore import ClaudeignoreGenerator, detect_project_types


def test_python_project_patterns(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]")
    gen = ClaudeignoreGenerator()
    result = gen.generate(tmp_path)
    assert "**/__pycache__/**" in result
    assert ".ruff_cache/" in result


def test_node_project_patterns(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    gen = ClaudeignoreGenerator()
    result = gen.generate(tmp_path)
    assert "node_modules/" in result
    assert ".next/" in result


def test_always_patterns_included(tmp_path):
    gen = ClaudeignoreGenerator()
    result = gen.generate(tmp_path)
    assert ".git/" in result
    assert "*.log" in result


def test_generic_fallback(tmp_path):
    types = detect_project_types(tmp_path)
    assert types == ["generic"]


def test_write_mirrors_to_geminiignore(tmp_path):
    gen = ClaudeignoreGenerator()
    content = gen.generate(tmp_path)
    gen.write(tmp_path, content)
    assert (tmp_path / ".claudeignore").exists()
    assert (tmp_path / ".geminiignore").exists()
    assert (tmp_path / ".claudeignore").read_text() == (tmp_path / ".geminiignore").read_text()
