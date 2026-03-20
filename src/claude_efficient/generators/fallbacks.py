"""Deterministic fallback functions — one per HelperTask. Never raises."""
from __future__ import annotations

import json

from claude_efficient.generators.backends import HelperRequest, HelperTask


def fallback_project_digest_root(content: str, context: dict) -> str:
    """Return content unchanged, truncated to 6 KB."""
    encoded = content.encode("utf-8")
    if len(encoded) > 6_144:
        return encoded[:6_144].decode("utf-8", errors="ignore")
    return content


def fallback_project_digest_subdir(content: str, context: dict) -> str:
    """Return content unchanged, truncated to 2 KB."""
    encoded = content.encode("utf-8")
    if len(encoded) > 2_048:
        return encoded[:2_048].decode("utf-8", errors="ignore")
    return content


def fallback_prompt_normalize(content: str, context: dict) -> str:
    """Return content stripped of leading/trailing whitespace."""
    return content.strip()


def fallback_task_shape_classify(content: str, context: dict) -> str:
    """Return unknown classification JSON."""
    return json.dumps({"shape": "unknown", "confidence": 0.0})


def fallback_mcp_relevance_classify(content: str, context: dict) -> str:
    """Return all MCPs as relevant."""
    relevant = context.get("mcp_names", [])
    return json.dumps({"relevant": relevant})


_DISPATCH: dict[HelperTask, object] = {
    HelperTask.project_digest_root:    fallback_project_digest_root,
    HelperTask.project_digest_subdir:  fallback_project_digest_subdir,
    HelperTask.prompt_normalize:       fallback_prompt_normalize,
    HelperTask.task_shape_classify:    fallback_task_shape_classify,
    HelperTask.mcp_relevance_classify: fallback_mcp_relevance_classify,
}


def _dispatch_fallback(request: HelperRequest) -> str:
    """Internal: dispatch to the correct fallback based on task type."""
    fn = _DISPATCH.get(request.task)
    if fn is None:
        return request.content
    return fn(request.content, request.context)  # type: ignore[operator]
