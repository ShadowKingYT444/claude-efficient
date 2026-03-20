from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_python_module_entrypoint_executes_click_cli() -> None:
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
        check=False,
    )

    assert result.returncode == 0
    assert "Usage:" in result.stdout
