from __future__ import annotations

from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from claude_efficient.cli.session import _fetch_mem_brief, run
from claude_efficient.config.defaults import HelperMode
from claude_efficient.generators.backends import DeterministicBackend

_NO_BACKEND = (HelperMode.off, DeterministicBackend())


def _mock_route(model: str = "claude-sonnet-4-6") -> MagicMock:
    decision = MagicMock()
    decision.model = model
    decision.reason = "test"
    decision.note = None
    return decision


def test_fetch_mem_brief_merges_queries_with_dedupe(tmp_path: Path):
    class FakeResponse:
        def __init__(self, payload: dict):
            self.ok = True
            self._payload = payload

        def json(self):
            return self._payload

    calls: list[str] = []

    def fake_post(_url, json, timeout):
        calls.append(json["query"])
        if len(calls) == 1:
            return FakeResponse(
                {
                    "results": [
                        {"summary": "Refactored auth middleware and fixed token refresh path."},
                        {"summary": "Refactored auth middleware and fixed token refresh path."},
                    ]
                }
            )
        return FakeResponse(
            {
                "results": [
                    {"summary": "Session used scoped MCP config to keep claude_mem active."},
                ]
            }
        )

    with patch("requests.post", side_effect=fake_post):
        brief = _fetch_mem_brief(
            "Fix auth.py regression and preserve claude_mem hooks",
            max_chars=180,
            root=tmp_path,
        )

    assert brief is not None
    assert len(brief) <= 180
    assert brief.count("Refactored auth middleware") == 1
    assert len(calls) >= 2


def test_run_enters_auto_prune_context_when_fast_path_disabled(tmp_path: Path):
    (tmp_path / "CLAUDE.md").write_text("# test")
    runner = CliRunner()
    entered = {"count": 0}

    @contextmanager
    def fake_auto_prune(*args, **kwargs):
        entered["count"] += 1
        session = MagicMock()
        session.auto_prune_enabled = True
        session.applied = True
        session.active_servers = ["claude_mem"]
        session.result = MagicMock(pruned=["github"])
        yield session

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "claude_efficient.cli.session.resolve_helpers_config",
                return_value=_NO_BACKEND,
            )
        )
        stack.enter_context(
            patch(
                "claude_efficient.cli.session.CacheHealthMonitor",
                return_value=MagicMock(check_all=MagicMock(return_value=MagicMock(risks=[]))),
            )
        )
        stack.enter_context(
            patch("claude_efficient.cli.session.route", return_value=_mock_route())
        )
        stack.enter_context(
            patch(
                "claude_efficient.cli.session.SessionScopeAnalyzer",
                return_value=MagicMock(estimate=MagicMock(return_value=MagicMock(warning=None))),
            )
        )
        stack.enter_context(
            patch(
                "claude_efficient.cli.session.classify_mcp_relevance",
                return_value=MagicMock(relevant=[]),
            )
        )
        stack.enter_context(
            patch(
                "claude_efficient.cli.session._read_enabled_mcps",
                return_value=["claude_mem", "github"],
            )
        )
        stack.enter_context(
            patch("claude_efficient.cli.session._fetch_mem_brief", return_value=None)
        )
        stack.enter_context(
            patch("claude_efficient.cli.session.auto_pruned_session_config", side_effect=fake_auto_prune)
        )
        mock_run = stack.enter_context(patch("subprocess.run"))
        stack.enter_context(
            patch.dict("os.environ", {"ENABLE_EXPERIMENTAL_MCP_CLI": "false"}, clear=False)
        )

        result = runner.invoke(run, ["--root", str(tmp_path), "fix auth bug"])

    assert result.exit_code == 0, result.output
    assert entered["count"] == 1
    assert mock_run.called
