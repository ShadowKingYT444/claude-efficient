from claude_efficient.generators.claude_md import ClaudeMdGenerator
from claude_efficient.generators.extractor import ExtractedFacts


def test_output_under_2000_bytes(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hi')")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'")

    facts = ExtractedFacts(
        tree=["src/", "pyproject.toml"],
        commands={"test": "pytest"},
        languages=["python"],
        key_configs=["pyproject.toml"],
    )
    # Helper returns more than 2000 bytes — must be trimmed
    def _big_helper(content: str) -> str | None:
        return "# Test\n" + "x" * 3000

    gen = ClaudeMdGenerator()
    result = gen.generate_root(facts, invoke_helper_fn=_big_helper)
    assert len(result.encode()) <= 2000


def test_output_under_2000_bytes_no_helper(tmp_path):
    facts = ExtractedFacts(
        tree=["src/", "pyproject.toml"],
        commands={"test": "pytest"},
        languages=["python"],
        key_configs=["pyproject.toml"],
    )
    gen = ClaudeMdGenerator()
    result = gen.generate_root(facts, invoke_helper_fn=None)
    assert len(result.encode()) <= 2000
    assert "#" in result


def test_write_creates_file(tmp_path):
    gen = ClaudeMdGenerator()
    gen.write(tmp_path, "# hello")
    assert (tmp_path / "CLAUDE.md").exists()


def test_generate_subdir_deterministic(tmp_path):
    from claude_efficient.generators.extractor import SubdirCandidate
    candidate = SubdirCandidate(path="src/api", language="python", file_count=6, qualifies=True)
    gen = ClaudeMdGenerator()
    result = gen.generate_subdir(candidate, invoke_helper_fn=None)
    assert "src/api" in result
    assert len(result.encode()) <= 600


def test_generate_subdir_trims_helper_output(tmp_path):
    from claude_efficient.generators.extractor import SubdirCandidate
    candidate = SubdirCandidate(path="src/api", language="python", file_count=6, qualifies=True)

    def _big_helper(content: str) -> str | None:
        return "x" * 1000

    gen = ClaudeMdGenerator()
    result = gen.generate_subdir(candidate, invoke_helper_fn=_big_helper)
    assert len(result.encode()) <= 600
