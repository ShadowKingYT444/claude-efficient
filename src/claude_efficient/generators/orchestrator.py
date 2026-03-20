"""Phase 3: Safe-auto orchestration layer.

Public surface: invoke_helper()

NOTE: ce status, ce audit, and claude-mem commands must NEVER call invoke_helper.
      This module is only for ce init and ce run.
"""
from __future__ import annotations

import logging

from claude_efficient.config.defaults import CAPS, HelperMode
from claude_efficient.generators.backends import (
    DeterministicBackend,
    HelperBackend,
    HelperRequest,
    HelperResponse,
    HelperTask,
)

logger = logging.getLogger(__name__)


def invoke_helper(
    task: HelperTask,
    content: str,
    context: dict = {},
    *,
    mode: HelperMode,
    backend: HelperBackend,
) -> HelperResponse:
    """
    Single entry point for all helper calls.

    mode=off       → skip model call; return deterministic fallback immediately
    mode=safe_auto → if len(content.encode()) > CAPS[task]: use deterministic fallback
                     else: call backend
    mode=force     → call backend regardless of input size; no cap check
    """
    input_bytes = len(content.encode("utf-8"))
    request = HelperRequest(task=task, content=content, context=context)

    if mode is HelperMode.off:
        response = DeterministicBackend().call(request)
    elif mode is HelperMode.safe_auto:
        cap = CAPS.get(task, 0)
        if input_bytes > cap:
            response = DeterministicBackend().call(request)
        else:
            if task not in backend.supported_tasks:
                response = DeterministicBackend().call(request)
            else:
                response = backend.call(request)
    else:  # force
        if task not in backend.supported_tasks:
            response = DeterministicBackend().call(request)
        else:
            response = backend.call(request)

    logger.debug(
        "[helper] task=%s mode=%s backend=%s model=%s used_fallback=%s input_bytes=%d",
        task.value,
        mode.value,
        response.backend_name,
        response.model_name,
        response.used_fallback,
        input_bytes,
    )
    return response
