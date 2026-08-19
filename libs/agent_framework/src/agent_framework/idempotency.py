from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from agent_framework.cache.cache import InMemoryCache, OracleCache, RedisCache, SQLiteCache

logger = logging.getLogger("agent_framework.idempotency")


class IdempotencyStore:
    """Namespace idempotente apoiado no storage genérico do framework."""

    def __init__(self, backend: Any, *, namespace: str = "idempotency", ttl_seconds: int | None = None):
        self.backend = backend
        self.namespace = namespace
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def canonical_key(*parts: Any) -> str:
        raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _key(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    async def get(self, key: str) -> Any | None:
        return await self.backend.get(self._key(key))

    async def set(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        await self.backend.set(self._key(key), value, ttl_seconds if ttl_seconds is not None else self.ttl_seconds)

    async def delete(self, key: str) -> None:
        await self.backend.delete(self._key(key))


class InMemoryIdempotencyStore(IdempotencyStore):
    def __init__(self, *, namespace: str = "idempotency", ttl_seconds: int | None = None):
        super().__init__(InMemoryCache(), namespace=namespace, ttl_seconds=ttl_seconds)


def create_idempotency_store(settings, *, namespace: str = "idempotency", require_durable: bool | None = None) -> IdempotencyStore:
    """Cria idempotência sem exigir configuração duplicada da aplicação.

    Precedência:
      IDEMPOTENCY_PROVIDER (quando definido)
      CHECKPOINT_REPOSITORY_PROVIDER
      SESSION_REPOSITORY_PROVIDER
      CACHE_BACKEND_PROVIDER

    Assim uma aplicação que já persiste LangGraph em Autonomous reaproveita o
    mesmo OracleStore para idempotência de efeitos externos.
    """
    provider = str(
        getattr(settings, "IDEMPOTENCY_PROVIDER", "")
        or getattr(settings, "CHECKPOINT_REPOSITORY_PROVIDER", "")
        or getattr(settings, "SESSION_REPOSITORY_PROVIDER", "")
        or getattr(settings, "CACHE_BACKEND_PROVIDER", "memory")
        or "memory"
    ).strip().lower()
    durable_required = bool(
        getattr(settings, "IDEMPOTENCY_REQUIRE_DURABLE", False)
        if require_durable is None else require_durable
    )
    ttl = int(getattr(settings, "IDEMPOTENCY_TTL_SECONDS", 86400) or 86400)

    if provider in {"autonomous", "oracle"}:
        backend = OracleCache(settings)
    elif provider == "redis":
        backend = RedisCache(settings)
    elif provider == "sqlite":
        backend = SQLiteCache(settings)
    elif provider in {"memory", "inmemory", ""}:
        if durable_required:
            raise RuntimeError("Idempotência durável requerida, mas nenhum provider durável está configurado")
        backend = InMemoryCache()
    else:
        if durable_required:
            raise RuntimeError(f"Provider de idempotência durável não suportado: {provider}")
        logger.warning("Provider de idempotência %s não suportado; usando memória", provider)
        backend = InMemoryCache()
    return IdempotencyStore(backend, namespace=namespace, ttl_seconds=ttl)
