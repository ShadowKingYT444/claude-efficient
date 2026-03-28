from pathlib import Path

from claude_efficient.analysis.waste_detector import WasteDetector


def test_detect_repetitive_tool_calls_finds_hot_tools_and_commands():
    transcript = """
    {"tool_name": "functions.shell_command", "command": "rtk grep foo src"}
    {"tool_name": "functions.shell_command", "command": "rtk grep foo src"}
    {"tool_name": "functions.shell_command", "command": "rtk grep foo src"}
    {"tool_name": "functions.shell_command", "command": "rtk grep foo src"}
    """
    finding = WasteDetector().detect_repetitive_tool_calls(transcript)
    assert finding is not None
    assert finding.category == "repetitive_tool_calls"
    assert finding.tokens_wasted > 0
    assert any("functions.shell_command" in evidence for evidence in finding.evidence)


def test_run_uses_billed_token_estimate_when_usage_exists(tmp_path: Path):
    transcript = tmp_path / "session.log"
    transcript.write_text(
        """
        {"role":"user","content":"do thing"}
        {"role":"assistant","content":"ok"}
        {"usage":{"input_tokens":1000,"output_tokens":150,"cache_read_input_tokens":700}}
        """
    )

    report = WasteDetector().run(transcript)
    assert report.total_tokens == 450
    assert report.billed_tokens == 450
    assert report.cache_read_tokens == 700
