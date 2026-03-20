"""Phase 1 + 2: HelperBackend abstraction and provider implementations."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

import requests as _requests

logger = logging.getLogger(__name__)


# ── Phase 1: Core types ──────────────────────────────────────────────────────

class HelperTask(Enum):
    project_digest_root    = "project_digest_root"
    project_digest_subdir  = "project_digest_subdir"
    prompt_normalize       = "prompt_normalize"
    task_shape_classify    = "task_shape_classify"
    mcp_relevance_classify = "mcp_relevance_classify"


@dataclass
class HelperRequest:
    task: HelperTask
    content: str   # extracted facts or prompt text; must be within cap before calling
    context: dict  # task-specific metadata (subdir path, available MCPs, etc.)


@dataclass
class HelperResponse:
    text: str
    backend_name: str  # e.g. "gemini", "ollama", "deterministic"
    model_name: str    # e.g. "gemini-2.5-flash-lite", "qwen2.5:3b", "n/a"
    used_fallback: bool


class HelperBackend(ABC):
    name: str
    supported_tasks: set[HelperTask]

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def call(self, request: HelperRequest) -> HelperResponse:
        """Must never raise. Catch internally and return used_fallback=True on error."""
        ...


# ── Phase 2: Provider implementations ────────────────────────────────────────

class GeminiFlashLiteBackend(HelperBackend):
    name = "gemini"
    supported_tasks = set(HelperTask)

    def __init__(self, model: str = "gemini-2.5-flash-lite") -> None:
        self._model = model

    def available(self) -> bool:
        return bool(os.environ.get("GEMINI_API_KEY", "").strip())

    def call(self, request: HelperRequest) -> HelperResponse:
        from claude_efficient.generators.fallbacks import _dispatch_fallback
        try:
            api_key = os.environ["GEMINI_API_KEY"]
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self._model}:generateContent?key={api_key}"
            )
            prompt = f"Task: {request.task.value}\n\n{request.content}"
            body = {"contents": [{"parts": [{"text": prompt}]}]}
            resp = _requests.post(url, json=body, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return HelperResponse(
                text=text.strip(),
                backend_name=self.name,
                model_name=self._model,
                used_fallback=False,
            )
        except Exception as exc:
            logger.warning("[helper] gemini call failed: %s", exc)
            fallback_text = _dispatch_fallback(request)
            return HelperResponse(
                text=fallback_text,
                backend_name=self.name,
                model_name=self._model,
                used_fallback=True,
            )


class OllamaBackend(HelperBackend):
    name = "ollama"
    supported_tasks = set(HelperTask)
    _ENDPOINT = "http://localhost:11434"

    def __init__(
        self,
        model: str = "qwen2.5:3b",
        fallback_model: str = "phi3:mini",
    ) -> None:
        self._model = model
        self._fallback_model = fallback_model

    def available(self) -> bool:
        try:
            return _requests.get(f"{self._ENDPOINT}/api/tags", timeout=2).ok
        except Exception:
            return False

    def call(self, request: HelperRequest) -> HelperResponse:
        from claude_efficient.generators.fallbacks import _dispatch_fallback
        prompt = f"Task: {request.task.value}\n\n{request.content}"

        for model in (self._model, self._fallback_model):
            try:
                resp = _requests.post(
                    f"{self._ENDPOINT}/api/generate",
                    json={"model": model, "prompt": prompt, "stream": False},
                    timeout=30,
                )
                resp.raise_for_status()
                text = resp.json().get("response", "").strip()
                return HelperResponse(
                    text=text,
                    backend_name=self.name,
                    model_name=model,
                    used_fallback=False,
                )
            except Exception as exc:
                logger.warning("[helper] ollama model=%s failed: %s", model, exc)

        fallback_text = _dispatch_fallback(request)
        return HelperResponse(
            text=fallback_text,
            backend_name=self.name,
            model_name=self._model,
            used_fallback=True,
        )


class OpenCodeBackend(HelperBackend):
    name = "opencode"
    supported_tasks = set(HelperTask)

    def __init__(self, command: list[str], args: list[str], model: str) -> None:
        self._command = command
        self._args = args
        self._model = model

    def available(self) -> bool:
        if not self._command or not self._model:
            return False
        return shutil.which(self._command[0]) is not None

    def call(self, request: HelperRequest) -> HelperResponse:
        from claude_efficient.generators.fallbacks import _dispatch_fallback
        try:
            interpolated = [
                a.replace("{model}", self._model) for a in self._args
            ]
            cmd = self._command + interpolated
            result = subprocess.run(
                cmd,
                input=request.content,
                capture_output=True,
                text=True,
                timeout=60,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0:
                raise RuntimeError(f"opencode exit {result.returncode}: {result.stderr[:200]}")
            return HelperResponse(
                text=result.stdout.strip(),
                backend_name=self.name,
                model_name=self._model,
                used_fallback=False,
            )
        except Exception as exc:
            logger.warning("[helper] opencode call failed: %s", exc)
            fallback_text = _dispatch_fallback(request)
            return HelperResponse(
                text=fallback_text,
                backend_name=self.name,
                model_name=self._model,
                used_fallback=True,
            )


class DeterministicBackend(HelperBackend):
    """Always available; wraps fallbacks module. Never makes external calls."""
    name = "deterministic"
    supported_tasks = set(HelperTask)

    def available(self) -> bool:
        return True

    def call(self, request: HelperRequest) -> HelperResponse:
        from claude_efficient.generators.fallbacks import _dispatch_fallback
        text = _dispatch_fallback(request)
        return HelperResponse(
            text=text,
            backend_name=self.name,
            model_name="n/a",
            used_fallback=True,
        )
