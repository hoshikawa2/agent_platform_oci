from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from motor.motor_asyncio import AsyncIOMotorClient
import json


def utcnow():
    return datetime.now(timezone.utc)


class MongoDBStore:
    def __init__(self, settings):
        self.client = AsyncIOMotorClient(settings.MONGODB_URI)
        self.db = self.client[settings.MONGODB_DATABASE]

        self.sessions = self.db["agent_sessions"]
        self.messages = self.db["agent_messages"]
        self.checkpoints = self.db["workflow_checkpoints"]
        self.checkpoint_writes = self.db["workflow_checkpoint_writes"]
        self.sse_events = self.db["sse_events"]
        self.cache = self.db["cache_entries"]
        self.usage = self.db["usage_events"]
        self.rag_documents = self.db["rag_documents"]
        self.graph_nodes = self.db["graph_nodes"]
        self.graph_edges = self.db["graph_edges"]

    async def init_schema(self):
        await self.sessions.create_index("session_id", unique=True)
        await self.messages.create_index([("session_id", 1), ("created_at", 1)])
        await self.messages.create_index("message_id")
        await self.checkpoints.create_index([("thread_id", 1), ("created_at", -1)])
        await self.sse_events.create_index([("session_id", 1), ("id", 1)])
        await self.cache.create_index("cache_key", unique=True)
        await self.rag_documents.create_index("namespace")
        await self.graph_nodes.create_index("node_id", unique=True)
        await self.graph_edges.create_index([("src", 1), ("rel", 1), ("dst", 1)])

    async def upsert_session(self, session_id: str, data: dict[str, Any]):
        data = {**data, "session_id": session_id, "updated_at": utcnow()}
        data.setdefault("created_at", utcnow())
        await self.sessions.update_one(
            {"session_id": session_id},
            {"$set": data, "$setOnInsert": {"created_at": utcnow()}},
            upsert=True,
        )

    async def get_session(self, session_id: str):
        doc = await self.sessions.find_one({"session_id": session_id}, {"_id": 0})
        return doc

    async def append_message(self, session_id: str, message: dict[str, Any]):
        doc = {
            **message,
            "session_id": session_id,
            "created_at": message.get("created_at") or utcnow(),
        }
        await self.messages.insert_one(doc)

    async def list_messages(self, session_id: str, limit: int = 50):
        cursor = (
            self.messages
            .find({"session_id": session_id}, {"_id": 0})
            .sort("created_at", 1)
            .limit(limit)
        )
        return [doc async for doc in cursor]

    async def put_checkpoint(self, thread_id: str, payload: dict[str, Any]):
        doc = {
            **payload,
            "thread_id": thread_id,
            "created_at": utcnow(),
        }
        await self.checkpoints.insert_one(doc)

    async def get_latest_checkpoint(self, thread_id: str):
        return await self.checkpoints.find_one(
            {"thread_id": thread_id},
            {"_id": 0},
            sort=[("created_at", -1)],
        )

    async def append_sse_event(self, session_id: str, event: str, payload: dict[str, Any]):
        seq = await self.db["counters"].find_one_and_update(
            {"_id": f"sse:{session_id}"},
            {"$inc": {"value": 1}},
            upsert=True,
            return_document=True,
        )
        event_id = seq["value"]

        await self.sse_events.insert_one({
            "id": event_id,
            "session_id": session_id,
            "event_name": event,
            "payload": payload,
            "created_at": utcnow(),
        })
        return event_id

    async def list_sse_events(self, session_id: str, after_id: int = 0, limit: int = 100):
        cursor = (
            self.sse_events
            .find(
                {"session_id": session_id, "id": {"$gt": after_id}},
                {"_id": 0},
            )
            .sort("id", 1)
            .limit(limit)
        )
        return [doc async for doc in cursor]