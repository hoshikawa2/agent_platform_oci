from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import datetime
from evaluator.core.models import ConversationRecord

class ConversationCollector(ABC):
    @abstractmethod
    async def collect(self, period_start: datetime, period_end: datetime, agent_aliases: set[str] | None = None, limit: int | None = None) -> list[ConversationRecord]: ...
