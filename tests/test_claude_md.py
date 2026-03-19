from unittest.mock import MagicMock
from claude_efficient.generators.claude_md import ClaudeMdGenerator


def test_output_under_2000_bytes(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hi')")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'")

    backend = MagicMock()
    backend._build_payload.return_value = "payload"
    backend.summarize.return_value = "# Test\n" + "x" * 3000  # over limit

    gen = ClaudeMdGenerator()
    result = gen.generate(tmp_path, backend)
    assert len(result.encode()) <= 2000


def test_write_creates_file(tmp_path):
    gen = ClaudeMdGenerator()
    gen.write(tmp_path, "# hello")
    assert (tmp_path / "CLAUDE.md").exists()
