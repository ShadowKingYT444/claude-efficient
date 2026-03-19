# tests/test_optimizer.py
from claude_efficient.prompt.optimizer import optimize

def test_filler_stripped():
    opt = optimize("please can you just build auth.py")
    assert "please" not in opt.text
    assert "can you" not in opt.text
    assert "just" not in opt.text
    assert "build auth.py" in opt.text

def test_short_prompt_warns():
    opt = optimize("build auth")
    assert any("Vague prompt" in w for w in opt.warnings)

def test_long_prompt_warns():
    long_prompt = "build auth.py. " + "x" * 1500
    opt = optimize(long_prompt)
    assert any("Long prompt" in w for w in opt.warnings)

def test_hint_appended_when_missing():
    opt = optimize("build auth.py proper functionality")
    assert "Output: code only" in opt.text
