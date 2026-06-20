from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

logger = logging.getLogger("agent_framework.analytics.tim_sequence")

# In-process fallback. This is not cross-process/global, but keeps telemetry alive
# when the configured shared sequence backend is unavailable, matching the
# framework principle that observability must not break business execution.
_memory_lock = asyncio.Lock()
_memory_counters: dict[str, int] = defaultdict(int)

SequenceProvider = Literal["auto", "redis", "mongodb", "mongo", "memory", "none"]


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def sequence_enabled() -> bool:
    return _env_bool("PUBSUB_SEQUENCE_ENABLED", True)


def _sequence_provider() -> SequenceProvider:
    raw = (os.getenv("PUBSUB_SEQUENCE_PROVIDER") or "auto").strip().lower()
    if raw in {"mongo"}:
        return "mongodb"
    if raw in {"auto", "redis", "mongodb", "memory", "none"}:
        return raw  # type: ignore[return-value]
    logger.warning("tim_sequence.invalid_provider provider=%s; using auto", raw)
    return "auto"


def _redis_url() -> str | None:
    return os.getenv("PUBSUB_SEQUENCE_REDIS_URL") or os.getenv("REDIS_URL")


def _mongo_uri() -> str | None:
    return (
        os.getenv("PUBSUB_SEQUENCE_MONGODB_URI")
        or os.getenv("MONGODB_URI")
        or os.getenv("MONGO_URI")
    )


def _mongo_database() -> str:
    return (
        os.getenv("PUBSUB_SEQUENCE_MONGODB_DATABASE")
        or os.getenv("MONGODB_DATABASE")
        or os.getenv("MONGO_DATABASE")
        or "agent_platform"
    )


def _legacy_agent_name() -> str:
    return _safe_part(os.getenv("AGENT_NAME") or "agent", "agent")


def _mongo_collection() -> str:
    """Return the MongoDB collection used for observer sequence counters.

    TIM legacy deployments used an agent-specific collection name, commonly
    ``{agent_name}_event_counters``. Keep an explicit env override for BO
    environments that already provisioned the collection, and fall back to the
    legacy naming convention when no collection is configured.
    """
    return (
        os.getenv("PUBSUB_SEQUENCE_MONGODB_COLLECTION")
        or os.getenv("MONGODB_EVENT_COUNTERS_COLLECTION")
        or os.getenv("EVENT_COUNTERS_COLLECTION")
        or f"{_legacy_agent_name()}_event_counters"
    )


def _ttl_seconds() -> int:
    raw = os.getenv("PUBSUB_SEQUENCE_TTL_SECONDS") or os.getenv("SESSION_TTL_SECONDS") or "86400"
    try:
        return max(0, int(raw))
    except Exception:
        return 86400


def _fallback_enabled() -> bool:
    return _env_bool("PUBSUB_SEQUENCE_MEMORY_FALLBACK", True)


def _key_prefix() -> str:
    return os.getenv("PUBSUB_SEQUENCE_KEY_PREFIX") or "observer:sequence"


def _safe_part(value: Any, fallback: str) -> str:
    text = str(value or fallback).strip()
    return text.replace(" ", "_").replace("/", "_").replace("\\", "_")


def build_sequence_key(agent_id: str | None, session_id: str) -> str:
    agent = _safe_part(agent_id or os.getenv("AGENT_NAME"), "agent")
    session = _safe_part(session_id, "unknown_session")
    return f"{_key_prefix()}:{agent}:{session}"


async def _next_sequence_redis(key: str, ttl_seconds: int) -> int | None:
    url = _redis_url()
    if not url:
        return None
    try:
        import redis.asyncio as redis_async  # type: ignore

        client = redis_async.Redis.from_url(url, decode_responses=True)
        try:
            value = await client.incr(key)
            if ttl_seconds > 0 and value == 1:
                await client.expire(key, ttl_seconds)
            return int(value)
        finally:
            try:
                await client.aclose()
            except AttributeError:  # redis-py older compatibility
                await client.close()
    except Exception:
        logger.exception("tim_sequence.redis_failed key=%s", key)
        return None


_mongo_index_checked = False
_mongo_index_lock = asyncio.Lock()


def _next_sequence_mongodb_sync(
    key: str,
    agent_id: str | None,
    session_id: str,
    ttl_seconds: int,
) -> int | None:
    uri = _mongo_uri()
    if not uri:
        return None

    from pymongo import MongoClient, ReturnDocument  # type: ignore

    client = MongoClient(uri)
    try:
        collection = client[_mongo_database()][_mongo_collection()]
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl_seconds) if ttl_seconds > 0 else None

        update: dict[str, Any] = {
            "$inc": {"sequence": 1},
            "$set": {
                "agentId": agent_id or os.getenv("AGENT_NAME") or "agent",
                "sessionId": session_id,
                "updatedAt": now,
            },
            "$setOnInsert": {
                "_id": key,
                "createdAt": now,
            },
        }
        if expires_at is not None:
            update["$set"]["expiresAt"] = expires_at

        doc = collection.find_one_and_update(
            {"_id": key},
            update,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if not doc:
            return None
        return int(doc.get("sequence", 0))
    finally:
        client.close()


async def _ensure_mongo_ttl_index_once(ttl_seconds: int) -> None:
    """Best-effort TTL index creation for Mongo sequence docs.

    The sequence still works without this index. If the application user lacks
    index privileges, we only log and continue.
    """
    global _mongo_index_checked
    if _mongo_index_checked or ttl_seconds <= 0 or not _mongo_uri():
        return

    async with _mongo_index_lock:
        if _mongo_index_checked:
            return
        try:
            from pymongo import MongoClient  # type: ignore

            def _create() -> None:
                client = MongoClient(_mongo_uri())
                try:
                    collection = client[_mongo_database()][_mongo_collection()]
                    collection.create_index("expiresAt", expireAfterSeconds=0, background=True)
                finally:
                    client.close()

            await asyncio.to_thread(_create)
        except Exception:
            logger.warning("tim_sequence.mongodb_ttl_index_failed", exc_info=True)
        finally:
            _mongo_index_checked = True


async def _next_sequence_mongodb(
    key: str,
    agent_id: str | None,
    session_id: str,
    ttl_seconds: int,
) -> int | None:
    if not _mongo_uri():
        return None
    try:
        await _ensure_mongo_ttl_index_once(ttl_seconds)
        return await asyncio.to_thread(
            _next_sequence_mongodb_sync,
            key,
            agent_id,
            session_id,
            ttl_seconds,
        )
    except Exception:
        logger.exception("tim_sequence.mongodb_failed key=%s", key)
        return None


async def _next_sequence_memory(key: str) -> int:
    async with _memory_lock:
        _memory_counters[key] += 1
        return _memory_counters[key]


async def next_sequence(agent_id: str | None, session_id: str | None) -> int | None:
    """Return the next per-agent/per-session observer sequence.

    Shared backends:
    - Redis: atomic INCR, selected by PUBSUB_SEQUENCE_PROVIDER=redis.
    - MongoDB: atomic find_one_and_update/$inc, selected by
      PUBSUB_SEQUENCE_PROVIDER=mongodb. This mirrors the TIM legacy behavior.

    Provider selection:
    - auto (default): Redis when configured; otherwise MongoDB when configured;
      otherwise memory fallback when enabled.
    - redis: Redis only, then memory fallback when enabled.
    - mongodb/mongo: MongoDB only, then memory fallback when enabled.
    - memory: in-process only.
    - none: disabled.

    If session_id is absent or the shared backend fails and memory fallback is
    disabled, None is returned so the payload remains valid without sequence.
    """
    if not sequence_enabled() or not session_id:
        return None

    provider = _sequence_provider()
    if provider == "none":
        return None

    key = build_sequence_key(agent_id, session_id)
    ttl_seconds = _ttl_seconds()
    value: int | None = None

    if provider == "memory":
        return await _next_sequence_memory(key)

    if provider == "redis":
        value = await _next_sequence_redis(key, ttl_seconds)
    elif provider == "mongodb":
        value = await _next_sequence_mongodb(key, agent_id, session_id, ttl_seconds)
    else:  # auto
        if _redis_url():
            value = await _next_sequence_redis(key, ttl_seconds)
        if value is None and _mongo_uri():
            value = await _next_sequence_mongodb(key, agent_id, session_id, ttl_seconds)

    if value is not None:
        return value
    if _fallback_enabled():
        return await _next_sequence_memory(key)
    return None


async def ensure_sequence(payload: dict[str, Any]) -> dict[str, Any]:
    """Inject sequence if missing, preserving explicit values from metadata/body."""
    if not isinstance(payload, dict):
        return payload
    if payload.get("sequence") is not None:
        return payload
    session_id = payload.get("sessionId") or payload.get("session_id")
    agent_id = payload.get("agentId") or payload.get("agent_id") or os.getenv("AGENT_NAME")
    seq = await next_sequence(agent_id, session_id)
    if seq is not None:
        payload["sequence"] = seq
    return payload
