```python
# src/claude_efficient/session/session.py
import logging
from typing import Any, Dict, List, Optional, Tuple

from .base_session import BaseSession
from .conversation_buffer import ConversationBuffer
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class ClaudeEfficientSession(BaseSession):
    """
    A session manager for interacting with Claude models efficiently.

    This class handles conversation history, rate limiting, and provides
    a structured way to send messages and receive responses.
    """

    def __init__(
        self,
        api_key