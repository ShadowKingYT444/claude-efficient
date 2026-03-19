# tests/test_compact_manager.py
from claude_efficient.session.compact_manager import CompactManager, CompactAction, SessionScopeAnalyzer

def test_healthy_below_threshold():
    assert CompactManager().check(0.30).action == CompactAction.NONE

def test_suggests_clear_at_threshold():
    state = CompactManager().check(0.50, "task complete")
    assert state.action == CompactAction.SUGGEST_CLEAR

def test_danger_threshold():
    assert CompactManager().check(0.75).action == CompactAction.DANGER

def test_mid_write_warns_not_clears():
    state = CompactManager().check(0.50, "building the module")
    assert state.action == CompactAction.WARN

def test_scope_analyzer_warns_large_task():
    analyzer = SessionScopeAnalyzer()
    est = analyzer.estimate(
        "Build auth.py, user.py, session.py, middleware.py, "
        "tokens.py, refresh.py and also update tests for all of them"
    )
    assert est.warning is not None
