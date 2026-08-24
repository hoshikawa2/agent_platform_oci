from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class ConversationSummaryRecord:
    """Resumo incremental associado a uma sessão conversacional."""

    session_id: str
    summary: str = ""
    last_message_created_at: str | None = None
    message_count_summarized: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class ConversationSummaryStore(ABC):
    """Contrato de persistência para resumos de memória conversacional."""

    @abstractmethod
    async def get(self, session_id: str) -> ConversationSummaryRecord | None: ...

    @abstractmethod
    async def upsert(self, record: ConversationSummaryRecord) -> None: ...

    async def delete(self, session_id: str) -> None:
        """Opcional para providers que suportarem limpeza explícita."""
        return None


class InMemoryConversationSummaryStore(ConversationSummaryStore):
    def __init__(self):
        self._data: dict[str, ConversationSummaryRecord] = {}

    async def get(self, session_id: str) -> ConversationSummaryRecord | None:
        return self._data.get(session_id)

    async def upsert(self, record: ConversationSummaryRecord) -> None:
        now = _utcnow_iso()
        existing = self._data.get(record.session_id)
        record.created_at = record.created_at or (existing.created_at if existing else now)
        record.updated_at = now
        self._data[record.session_id] = record

    async def delete(self, session_id: str) -> None:
        self._data.pop(session_id, None)


class SQLiteConversationSummaryStore(ConversationSummaryStore):
    def __init__(self, settings):
        from agent_framework.persistence.sqlite_store import SQLiteStore

        self.store = SQLiteStore(settings.SQLITE_DB_PATH)

    async def get(self, session_id: str) -> ConversationSummaryRecord | None:
        row = self.store.get_memory_summary(session_id)
        return ConversationSummaryRecord(**row) if row else None

    async def upsert(self, record: ConversationSummaryRecord) -> None:
        self.store.upsert_memory_summary(
            session_id=record.session_id,
            summary=record.summary,
            last_message_created_at=record.last_message_created_at,
            message_count_summarized=record.message_count_summarized,
            metadata=record.metadata,
        )

    async def delete(self, session_id: str) -> None:
        self.store.delete_memory_summary(session_id)


class OracleConversationSummaryStore(ConversationSummaryStore):
    def __init__(self, settings):
        from agent_framework.persistence.oracle_store import OracleStore

        self.store = OracleStore(settings)

    async def get(self, session_id: str) -> ConversationSummaryRecord | None:
        row = await self.store.get_memory_summary(session_id)
        return ConversationSummaryRecord(**row) if row else None

    async def upsert(self, record: ConversationSummaryRecord) -> None:
        await self.store.upsert_memory_summary(
            session_id=record.session_id,
            summary=record.summary,
            last_message_created_at=record.last_message_created_at,
            message_count_summarized=record.message_count_summarized,
            metadata=record.metadata,
        )

    async def delete(self, session_id: str) -> None:
        await self.store.delete_memory_summary(session_id)


class MongoConversationSummaryStore(ConversationSummaryStore):
    def __init__(self, settings):
        from pymongo import MongoClient

        self.client = MongoClient(settings.MONGODB_URI)
        self.col = self.client[settings.MONGODB_DATABASE]["memory_summaries"]
        self.col.create_index("session_id", unique=True)

    async def get(self, session_id: str) -> ConversationSummaryRecord | None:
        doc = self.col.find_one({"session_id": session_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return ConversationSummaryRecord(**doc)

    async def upsert(self, record: ConversationSummaryRecord) -> None:
        now = _utcnow_iso()
        existing = self.col.find_one({"session_id": record.session_id})
        doc = {
            "session_id": record.session_id,
            "summary": record.summary,
            "last_message_created_at": record.last_message_created_at,
            "message_count_summarized": record.message_count_summarized,
            "metadata": record.metadata or {},
            "created_at": record.created_at or (existing or {}).get("created_at") or now,
            "updated_at": now,
        }
        self.col.update_one({"session_id": record.session_id}, {"$set": doc}, upsert=True)

    async def delete(self, session_id: str) -> None:
        self.col.delete_one({"session_id": session_id})


def create_summary_store(settings) -> ConversationSummaryStore:
    provider = getattr(settings, "MEMORY_REPOSITORY_PROVIDER", "memory")
    if provider == "mongodb":
        return MongoConversationSummaryStore(settings)
    if provider == "sqlite":
        return SQLiteConversationSummaryStore(settings)
    if provider in {"autonomous", "oracle"}:
        return OracleConversationSummaryStore(settings)
    return InMemoryConversationSummaryStore()
