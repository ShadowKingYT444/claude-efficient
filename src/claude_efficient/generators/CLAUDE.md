```python
# src/claude_efficient/generators/base.py
import abc
from typing import Any, Dict, Generator, List, Optional

from pydantic import BaseModel


class GeneratorConfig(BaseModel):
    """Base configuration for any generator."""

    pass


class Generator(abc.ABC):
    """Abstract base class for all generators."""

    def __init__(self, config: GeneratorConfig):
        self.config = config

    @abc.abstractmethod
    def generate(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        """Generate text based on the given prompt."""
        pass

    @abc.abstractmethod
   