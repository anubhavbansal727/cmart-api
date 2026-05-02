from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMClient(ABC):
    @abstractmethod
    async def invoke(self, prompt: str) -> str:
        """Generate a plain text response."""
        ...

    @abstractmethod
    async def invoke_structured(self, prompt: str, schema: type[T]) -> T:
        """Generate a structured response conforming to schema."""
        ...
