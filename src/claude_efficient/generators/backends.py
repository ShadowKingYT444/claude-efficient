from abc import ABC, abstractmethod
from pathlib import Path
import shutil
import subprocess
import sys

import requests as _requests


class Backend(ABC):
    name: str
    supports_large_context: bool = False

    @staticmethod
    @abstractmethod
    def is_available() -> bool: ...

    @abstractmethod
    def summarize(self, prompt: str, payload: str) -> str: ...

    def _build_payload(
        self,
        root: Path,
        file_tree: str,
        key_files: list[Path],
        max_files: int = 20,
        max_chars_per_file: int = 3000,
    ) -> str:
        parts = [f"FILE TREE:\n{file_tree}\n\nKEY FILE CONTENTS:\n"]
        for path in key_files[:max_files]:
            try:
                content = path.read_text(errors="replace")[:max_chars_per_file]
                parts.append(f"--- {path.relative_to(root)} ---\n{content}\n")
            except Exception:
                pass
        return "\n".join(parts)


class GeminiBackend(Backend):
    name = "gemini"
    supports_large_context = True
    MODEL = "gemini-2.5-pro"

    @staticmethod
    def is_available() -> bool:
        return shutil.which("gemini") is not None

    def summarize(self, prompt: str, payload: str) -> str:
        # prompt as -p arg (short), payload via stdin (bypasses Windows 32KB cmd limit)
        result = subprocess.run(
            ["gemini", "-p", prompt, "--output-format", "text", "--model", self.MODEL],
            input=payload,
            capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace",
            shell=(sys.platform == "win32"),
        )
        if result.returncode != 0:
            raise RuntimeError(f"Gemini error: {result.stderr[:200]}")
        return result.stdout.strip()


class OllamaBackend(Backend):
    name = "ollama"
    MODEL = "qwen2.5:3b"
    MAX_PAYLOAD_CHARS = 6_000

    @staticmethod
    def is_available() -> bool:
        try:
            return _requests.get("http://localhost:11434/api/tags", timeout=2).ok
        except Exception:
            return False

    def summarize(self, prompt: str, payload: str) -> str:
        clipped = payload[:self.MAX_PAYLOAD_CHARS]
        r = _requests.post(
            "http://localhost:11434/api/generate",
            json={"model": self.MODEL, "prompt": f"{prompt}\n\n{clipped}", "stream": False},
            timeout=180,
        )
        r.raise_for_status()
        return r.json().get("response", "").strip()


class LLMBackend(Backend):
    name = "llm"
    MAX_PAYLOAD_CHARS = 8_000

    @staticmethod
    def is_available() -> bool:
        return shutil.which("llm") is not None

    def summarize(self, prompt: str, payload: str) -> str:
        clipped = payload[:self.MAX_PAYLOAD_CHARS]
        result = subprocess.run(
            ["llm", "-s", prompt],
            input=clipped,
            capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace",
            shell=(sys.platform == "win32"),
        )
        if result.returncode != 0:
            raise RuntimeError(f"llm error: {result.stderr[:200]}")
        return result.stdout.strip()


class ClaudeBackend(Backend):
    name = "claude"

    @staticmethod
    def is_available() -> bool:
        return shutil.which("claude") is not None

    def summarize(self, prompt: str, payload: str) -> str:
        import click
        click.secho("[ce] WARNING: Using Claude Code for init — costs real tokens.", fg="yellow")
        click.secho("[ce] Install Gemini CLI for free init: npm i -g @google/gemini-cli", fg="yellow")
        result = subprocess.run(
            ["claude", "-p", prompt],
            input=payload[:6000],
            capture_output=True, text=True, timeout=180,
            encoding="utf-8", errors="replace",
            shell=(sys.platform == "win32"),
        )
        return result.stdout.strip()


BACKEND_PRIORITY: list[type[Backend]] = [
    GeminiBackend,
    OllamaBackend,
    LLMBackend,
    ClaudeBackend,
]


def detect_backend() -> Backend:
    for cls in BACKEND_PRIORITY:
        if cls.is_available():
            return cls()
    raise RuntimeError(
        "No backend found. Install: npm i -g @google/gemini-cli  OR  ollama pull qwen2.5:3b"
    )
