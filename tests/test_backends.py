from unittest.mock import patch
from claude_efficient.generators.backends import GeminiFlashLiteBackend, OllamaBackend


def test_gemini_backend_available_with_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    backend = GeminiFlashLiteBackend()
    assert backend.available() is True


def test_gemini_backend_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    backend = GeminiFlashLiteBackend()
    assert backend.available() is False


def test_ollama_backend_available_when_up():
    with patch("requests.get") as mock_get:
        mock_get.return_value.ok = True
        backend = OllamaBackend()
        assert backend.available() is True


def test_ollama_backend_unavailable_when_down():
    with patch("requests.get") as mock_get:
        mock_get.side_effect = Exception("Down")
        backend = OllamaBackend()
        assert backend.available() is False
