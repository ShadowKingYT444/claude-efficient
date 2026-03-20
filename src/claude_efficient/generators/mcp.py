"""Phase 5: MCP relevance classification."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class McpRelevanceResult:
    relevant: list[str] = field(default_factory=list)
    used_fast_path: bool = False


def classify_mcp_relevance(
    prompt: str,
    available_mcps: list[str],
    *,
    invoke_helper_fn: Callable[[str], str] | None,
    fast_path_enabled: bool,
) -> McpRelevanceResult:
    """
    Fast path (env flag): return all MCPs as relevant (existing behavior).
    Helper path: use invoke_helper for mcp_relevance_classify.
    Deterministic fallback: return all MCPs as relevant.
    Input cap: 1 KB (enforced by orchestrator).
    """
    if fast_path_enabled:
        return McpRelevanceResult(relevant=list(available_mcps), used_fast_path=True)
    if not available_mcps:
        return McpRelevanceResult(relevant=[], used_fast_path=False)
    if invoke_helper_fn is None:
        return McpRelevanceResult(relevant=list(available_mcps), used_fast_path=False)
    try:
        input_text = f"Prompt: {prompt}\nAvailable MCPs: {', '.join(available_mcps)}"
        raw = invoke_helper_fn(input_text)
        relevant = _parse_relevant_mcps(raw, available_mcps)
        return McpRelevanceResult(relevant=relevant, used_fast_path=False)
    except Exception:
        return McpRelevanceResult(relevant=list(available_mcps), used_fast_path=False)


def _parse_relevant_mcps(text: str, available: list[str]) -> list[str]:
    """Extract MCP names from helper output. Conservative: include all on ambiguity."""
    text_lower = text.lower()
    found = [mcp for mcp in available if mcp.lower() in text_lower]
    return found if found else list(available)
