from claude_efficient.generators.claude_md import ClaudeMdGenerator
from claude_efficient.generators.extractor import ExtractedFacts


def test_output_under_max_bytes(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hi')")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'")

    facts = ExtractedFacts(
        tree=["src/", "pyproject.toml"],
        commands={"test": "pytest"},
        languages=["python"],
        key_configs=["pyproject.toml"],
    )
    gen = ClaudeMdGenerator()
    # Helper returns more than MAX_BYTES — must be trimmed
    result = gen.generate_root(facts, project_summary="# Test\n" + "x" * 10000)
    assert len(result.encode()) <= ClaudeMdGenerator.MAX_BYTES


def test_output_under_max_bytes_no_helper(tmp_path):
    facts = ExtractedFacts(
        tree=["src/", "pyproject.toml"],
        commands={"test": "pytest"},
        languages=["python"],
        key_configs=["pyproject.toml"],
    )
    gen = ClaudeMdGenerator()
    result = gen.generate_root(facts, project_summary=None)
    assert len(result.encode()) <= ClaudeMdGenerator.MAX_BYTES
    assert "#" in result


def test_write_creates_file(tmp_path):
    gen = ClaudeMdGenerator()
    gen.write(tmp_path, "# hello")
    assert (tmp_path / "CLAUDE.md").exists()


def test_generate_subdir_deterministic(tmp_path):
    from claude_efficient.generators.extractor import SubdirCandidate
    candidate = SubdirCandidate(path="src/api", language="python", file_count=6, qualifies=True)
    gen = ClaudeMdGenerator()
    result = gen.generate_subdir(candidate, subdir_summary=None)
    assert "src/api" in result
    assert len(result.encode()) <= ClaudeMdGenerator.SUBDIR_MAX_BYTES


def test_generate_subdir_trims_helper_output(tmp_path):
    from claude_efficient.generators.extractor import SubdirCandidate
    candidate = SubdirCandidate(path="src/api", language="python", file_count=6, qualifies=True)

    gen = ClaudeMdGenerator()
    result = gen.generate_subdir(candidate, subdir_summary="x" * 5000)
    assert len(result.encode()) <= ClaudeMdGenerator.SUBDIR_MAX_BYTES
