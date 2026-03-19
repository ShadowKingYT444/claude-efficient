# tests/test_cache_health.py
import os
from unittest.mock import patch
from claude_efficient.analysis.cache_health import CacheHealthMonitor


def test_missing_experimental_flag_with_mcp_servers(tmp_path):
    monitor = CacheHealthMonitor()
    with patch.object(monitor, "_count_mcp_servers", return_value=8):
        with patch.dict(os.environ, {}, clear=True):
            report = monitor.check_all(tmp_path)
    codes = [r.code for r in report.risks]
    assert "missing_experimental_mcp_flag" in codes


def test_flag_set_no_mcp_risk(tmp_path):
    monitor = CacheHealthMonitor()
    with patch.object(monitor, "_count_mcp_servers", return_value=8):
        with patch.dict(os.environ, {"ENABLE_EXPERIMENTAL_MCP_CLI": "true"}):
            report = monitor.check_all(tmp_path)
    codes = [r.code for r in report.risks]
    assert "missing_experimental_mcp_flag" not in codes


def test_missing_claude_md_warns(tmp_path):
    report = CacheHealthMonitor().check_all(tmp_path)
    assert any(r.code == "missing_claude_md" for r in report.risks)


def test_oversized_claude_md_warns(tmp_path):
    (tmp_path / "CLAUDE.md").write_bytes(b"x" * 5_000)
    report = CacheHealthMonitor().check_all(tmp_path)
    assert any(r.code == "claude_md_too_large" for r in report.risks)


def test_healthy_session_no_risks(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# test\n")
    monitor = CacheHealthMonitor()
    with patch.object(monitor, "_count_mcp_servers", return_value=0):
        with patch.dict(os.environ, {"ENABLE_EXPERIMENTAL_MCP_CLI": "true"}):
            report = monitor.check_all(tmp_path)
    assert report.is_healthy