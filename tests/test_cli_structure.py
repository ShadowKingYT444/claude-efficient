import subprocess
import sys
import os
from pathlib import Path

def test_cli_default_commands_visible():
    project_root = Path(__file__).resolve().parents[1]
    source_root = project_root / "src"

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{source_root}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else str(source_root)
    )

    result = subprocess.run(
        [sys.executable, "-m", "claude_efficient.cli.main", "--help"],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    stdout = result.stdout
    # Core commands should be visible
    assert "init" in stdout
    assert "run" in stdout
    assert "gains" in stdout
    
    # Internal commands should be hidden
    assert "audit" not in stdout
    assert "helpers" not in stdout
    assert "mem-search" not in stdout
    assert "scope-check" not in stdout
    assert "status" not in stdout
    assert "telemetry" not in stdout

def test_cli_verbose_commands_visible():
    project_root = Path(__file__).resolve().parents[1]
    source_root = project_root / "src"

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{source_root}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else str(source_root)
    )

    result = subprocess.run(
        [sys.executable, "-m", "claude_efficient.cli.main", "--verbose", "--help"],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    stdout = result.stdout
    # All commands should be visible
    assert "init" in stdout
    assert "run" in stdout
    assert "gains" in stdout
    assert "audit" in stdout
    assert "helpers" in stdout
    assert "mem-search" in stdout
    assert "scope-check" in stdout
    assert "status" in stdout
    assert "telemetry" in stdout
