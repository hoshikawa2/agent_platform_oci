from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger("agent_framework.cache")


class Cache:
    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None: ...
    async def delete(self, key: str) -> None: ...


class InMemoryCache(Cache):
    def __init__(self):
        self._data: dict[str, tuple[Any, float | None]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key):
        async with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            value, expires = item
            if expires and expires < time.time():
                self._data.pop(key, None)
                return None
            return value

    async def set(self, key, value, ttl_seconds=None):
        async with self._lock:
            self._data[key] = (value, time.time() + ttl_seconds if ttl_seconds else None)

    async def delete(self, key):
        async with self._lock:
            self._data.pop(key, None)


class RedisCache(Cache):
    """Redis L2 cache with redis-py sync/async compatibility and safe fallback."""
    def __init__(self, settings):
        self.url = settings.REDIS_URL
        self.prefix = getattr(settings, "CACHE_KEY_PREFIX", "agentfw")
        self._async = False
        try:
            import redis.asyncio as redis_async
            self.client = redis_async.Redis.from_url(self.url, decode_responses=True)
            self._async = True
        except Exception:
            import redis
            self.client = redis.Redis.from_url(self.url, decode_responses=True)

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    async def get(self, key):
        try:
            raw = await self.client.get(self._key(key)) if self._async else await asyncio.to_thread(self.client.get, self._key(key))
            return json.loads(raw) if raw else None
        except Exception:
            logger.exception("Redis GET falhou key=%s", key)
            return None

    async def set(self, key, value, ttl_seconds=None):
        raw = json.dumps(value, ensure_ascii=False, default=str)
        try:
            if self._async:
                await self.client.set(self._key(key), raw, ex=ttl_seconds)
            else:
                await asyncio.to_thread(self.client.set, self._key(key), raw, ex=ttl_seconds)
        except Exception:
            logger.exception("Redis SET falhou key=%s", key)

    async def delete(self, key):
        try:
            if self._async:
                await self.client.delete(self._key(key))
            else:
                await asyncio.to_thread(self.client.delete, self._key(key))
        except Exception:
            logger.exception("Redis DELETE falhou key=%s", key)


class SQLiteCache(Cache):
    def __init__(self, settings):
        from agent_framework.persistence.sqlite_store import SQLiteStore
        self.store = SQLiteStore(settings.SQLITE_DB_PATH)

    async def get(self, key):
        return await asyncio.to_thread(self._get_sync, key)

    def _get_sync(self, key):
        with self.store._lock, self.store.connect() as con:
            row = con.execute("select value_json, expires_at from cache_entries where key=?", (key,)).fetchone()
            if not row:
                return None
            if row["expires_at"] and row["expires_at"] < time.time():
                con.execute("delete from cache_entries where key=?", (key,))
                return None
            return json.loads(row["value_json"])

    async def set(self, key, value, ttl_seconds=None):
        await asyncio.to_thread(self._set_sync, key, value, ttl_seconds)

    def _set_sync(self, key, value, ttl_seconds=None):
        expires = time.time() + ttl_seconds if ttl_seconds else None
        with self.store._lock, self.store.connect() as con:
            con.execute(
                "insert or replace into cache_entries(key,value_json,expires_at,created_at) values(?,?,?,?)",
                (key, json.dumps(value, ensure_ascii=False, default=str), expires, self.store.now()),
            )

    async def delete(self, key):
        await asyncio.to_thread(self._delete_sync, key)

    def _delete_sync(self, key):
        with self.store._lock, self.store.connect() as con:
            con.execute("delete from cache_entries where key=?", (key,))


class OracleCache(Cache):
    def __init__(self, settings):
        from agent_framework.persistence.oracle_store import OracleStore
        self.store = OracleStore(settings)

    async def get(self, key): return await self.store.cache_get(key)
    async def set(self, key, value, ttl_seconds=None):
        expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds) if ttl_seconds else None
        await self.store.cache_set(key, value, expires_at=expires)
    async def delete(self, key): await self.store.cache_delete(key)


class DistributedCache(Cache):
    """L1 memory + optional L2 Redis/SQLite/Oracle with telemetry hooks."""
    def __init__(self, l1: Cache, l2: Cache | None = None, telemetry=None, default_ttl: int | None = None):
        self.l1, self.l2, self.telemetry, self.default_ttl = l1, l2, telemetry, default_ttl

    async def get(self, key):
        v = await self.l1.get(key)
        if v is not None:
            if self.telemetry: await self.telemetry.cache_event("hit.l1", key, True)
            return v
        if not self.l2:
            if self.telemetry: await self.telemetry.cache_event("miss", key, False)
            return None
        v = await self.l2.get(key)
        if v is not None:
            await self.l1.set(key, v, self.default_ttl)
            if self.telemetry: await self.telemetry.cache_event("hit.l2", key, True)
            return v
        if self.telemetry: await self.telemetry.cache_event("miss", key, False)
        return None

    async def set(self, key, value, ttl_seconds=None):
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        await self.l1.set(key, value, ttl)
        if self.l2: await self.l2.set(key, value, ttl)
        if self.telemetry: await self.telemetry.cache_event("set", key, None, {"ttl_seconds": ttl})

    async def delete(self, key):
        await self.l1.delete(key)
        if self.l2: await self.l2.delete(key)
        if self.telemetry: await self.telemetry.cache_event("delete", key, None)


def create_cache(settings, telemetry=None):
    l1 = InMemoryCache()
    l2 = None
    if getattr(settings, "ENABLE_REDIS_CACHE", False):
        try:
            l2 = RedisCache(settings)
        except Exception:
            logger.exception("Redis indisponível; cache seguirá apenas com L1 memória")
            l2 = None
    if l2 is None:
        provider = getattr(settings, "CACHE_BACKEND_PROVIDER", "memory")
        if provider == "sqlite": l2 = SQLiteCache(settings)
        elif provider in {"autonomous", "oracle"}: l2 = OracleCache(settings)
    return DistributedCache(l1, l2, telemetry=telemetry, default_ttl=getattr(settings, "CACHE_TTL_SECONDS", None))
