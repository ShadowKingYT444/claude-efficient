from unittest.mock import patch
from claude_efficient.generators.backends import detect_backend, GeminiBackend, OllamaBackend


def test_detect_backend_picks_gemini_first():
    with patch.object(GeminiBackend, "is_available", return_value=True):
        backend = detect_backend()
        assert isinstance(backend, GeminiBackend)


def test_detect_backend_falls_through_to_ollama():
    with patch.object(GeminiBackend, "is_available", return_value=False), \
         patch.object(OllamaBackend, "is_available", return_value=True):
        backend = detect_backend()
        assert isinstance(backend, OllamaBackend)
