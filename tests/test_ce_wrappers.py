import json
import os

from claude_efficient.cli import ce_wrapper_core


def test_init_creates_cursor_marker_and_exports_agent_name(tmp_path):
    exit_code = ce_wrapper_core.run_wrapper_command(
        "cursor",
        "init",
        cwd=tmp_path,
        agent_name="review-agent",
    )
    assert exit_code == 0
    assert os.environ.get("CE_AGENT_NAME") == "review-agent"

    marker = tmp_path / ".ce-cursor-session"
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload["status"] == "idle"
    assert payload["agent_name"] == "review-agent"


def test_run_gemini_uses_headless_mode_and_marks_idle(tmp_path, monkeypatch):
    captured = {}

    class FakeProcess:
        pid = 4242

        def wait(self):
            return 0

    def fake_spawn(command, cwd, env):
        captured["command"] = command
        captured["cwd"] = cwd
        captured["env"] = env
        return FakeProcess()

    monkeypatch.setattr(ce_wrapper_core, "_spawn_process", fake_spawn)

    exit_code = ce_wrapper_core.run_wrapper_command(
        "gemini",
        "run",
        cwd=tmp_path,
        agent_name="scout-agent",
        task="Find all TODOs",
    )
    assert exit_code == 0
    # The prompt is optimized: added "Output: code only, no preamble."
    expected_task = "Find all TODOs\nOutput: code only, no preamble."
    assert captured["command"] == [
        "gemini",
        "--include-directories",
        str(tmp_path.resolve()),
        "--approval-mode",
        "auto",
        "-p",
        expected_task,
    ]
    assert captured["cwd"] == tmp_path.resolve()
    assert captured["env"]["CE_AGENT_NAME"] == "scout-agent"

    marker = tmp_path / ".ce-gemini-session"
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload["status"] == "idle"
    assert payload["pid"] is None


def test_status_reports_running_for_active_pid(tmp_path, capsys):
    marker = tmp_path / ".ce-gemini-session"
    marker.write_text(
        json.dumps(
            {
                "cli": "gemini",
                "cwd": str(tmp_path),
                "agent_name": "scout-agent",
                "status": "running",
                "pid": os.getpid(),
                "last_error": None,
                "updated_at": "2026-03-20T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    exit_code = ce_wrapper_core.run_wrapper_command("gemini", "status", cwd=tmp_path)
    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "running"


def test_status_for_unreadable_marker_returns_error(tmp_path, capsys):
    marker = tmp_path / ".ce-opencode-session"
    marker.write_text("this-is-not-json", encoding="utf-8")

    exit_code = ce_wrapper_core.run_wrapper_command("opencode", "status", cwd=tmp_path)
    assert exit_code == 1
    assert capsys.readouterr().out.strip() == "error"
