# tests/test_mcp_config.py
import os
from unittest.mock import patch
from claude_efficient.session.mcp_config import McpConfigAdvisor

def test_with_experimental_flag_no_overhead():
    advisor = McpConfigAdvisor()
    with patch.dict(os.environ, {"ENABLE_EXPERIMENTAL_MCP_CLI": "true"}):
        plan = advisor.plan_session("build auth.py", ["gmail", "claude_mem", "github"])
    assert plan.has_experimental_flag
    assert plan.tokens_overhead == 0
    assert plan.deferred_servers == []

def test_always_keep_never_deferred():
    advisor = McpConfigAdvisor()
    with patch.dict(os.environ, {}, clear=True):
        plan = advisor.plan_session("build auth.py", ["claude_mem", "gmail"])
    assert "claude_mem" in plan.active_servers
    assert "gmail" in plan.deferred_servers

def test_relevant_server_stays_active():
    advisor = McpConfigAdvisor()
    with patch.dict(os.environ, {}, clear=True):
        plan = advisor.plan_session("draft an email to the team", ["gmail", "github"])
    assert "gmail" in plan.active_servers
    assert "github" in plan.deferred_servers
