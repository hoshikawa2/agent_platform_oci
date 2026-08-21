from abc import ABC, abstractmethod
from typing import Any

from .types import LLMResponse


class LLMProvider(ABC):
    @abstractmethod
    async def ainvoke(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Legacy API. Must keep returning only the textual answer."""
        ...

    async def ainvoke_response(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> LLMResponse:
        """Rich opt-in API with a backward-compatible fallback.

        Custom providers that only implement ``ainvoke`` continue to work. They
        simply expose ``content`` and leave optional provider metadata/reasoning
        empty until they choose to override this method.
        """
        content = await self.ainvoke(messages, **kwargs)
        return LLMResponse(content=str(content or ""))
