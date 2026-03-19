# tests/test_model_router.py
from claude_efficient.session.model_router import route, SONNET, OPUS

def test_implementation_routes_to_sonnet():
    assert route("Build collectors/os_hook.py").model == SONNET

def test_architecture_routes_to_opus():
    assert route("architect the entire data pipeline").model == OPUS

def test_empty_prompt_defaults_to_sonnet():
    assert route("").model == SONNET

def test_planning_keyword_routes_to_opus():
    assert route("design the authentication system").model == OPUS

def test_route_is_stable_same_input():
    """Same prompt must always produce same model — routing must be deterministic."""
    assert route("Build auth.py") == route("Build auth.py")
