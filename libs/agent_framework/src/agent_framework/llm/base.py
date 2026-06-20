from abc import ABC, abstractmethod
from typing import Any

class LLMProvider(ABC):
    @abstractmethod
    async def ainvoke(self, messages: list[dict[str, str]], **kwargs: Any) -> str: ...
