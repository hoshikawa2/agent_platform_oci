from __future__ import annotations
try:
    from langgraph.checkpoint.base import BaseCheckpointSaver
except Exception:  # pragma: no cover - fallback for lightweight unit tests without langgraph installed
    class BaseCheckpointSaver:  # type: ignore[no-redef]
        pass

"""LangGraph checkpoint saver backed by the framework checkpoint repository.

This module intentionally keeps a small adapter surface so the framework can run
with multiple LangGraph versions. It implements the common synchronous and
asynchronous methods used by BaseCheckpointSaver/MemorySaver: get_tuple,
aget_tuple, put, aput, put_writes, aput_writes, list and alist.

The persisted payload stores LangGraph's raw checkpoint/config/metadata values in
repository-neutral JSON. When LangGraph is installed, checkpoint tuples are
returned using CheckpointTuple; otherwise a simple dict is returned for tests.
"""

import asyncio
import json
import uuid
from typing import Any, AsyncIterator, Iterator

from .checkpoint_repository import create_checkpoint_repository


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value, default=str)
        return value
    except TypeError:
        return json.loads(json.dumps(value, default=str))


def _thread_id(config: dict[str, Any] | None) -> str:
    configurable = (config or {}).get("configurable") or {}
    return str(configurable.get("thread_id") or configurable.get("checkpoint_ns") or "default")


def _checkpoint_id(checkpoint: dict[str, Any] | None) -> str:
    if isinstance(checkpoint, dict):
        return str(checkpoint.get("id") or checkpoint.get("checkpoint_id") or uuid.uuid4())
    return str(uuid.uuid4())


def _normalize_pending_writes(pending_writes: Any) -> list[tuple[Any, Any, Any]]:
    """Normalize persisted pending_writes to LangGraph's expected runtime format.

    LangGraph 1.1.x expects CheckpointTuple.pending_writes to be an iterable of
    3-item tuples: (task_id, channel, value).

    Older framework versions persisted writes as dictionaries containing
    task_id, task_path, channel and value. Some stores/tests may also contain
    4-item tuples: (task_id, task_path, channel, value). This adapter accepts
    those legacy forms while preserving already-correct 3-item tuples.
    """
    normalized: list[tuple[Any, Any, Any]] = []
    for item in pending_writes or []:
        if isinstance(item, dict):
            normalized.append((
                item.get("task_id"),
                item.get("channel"),
                item.get("value"),
            ))
            continue

        if isinstance(item, (list, tuple)):
            if len(item) == 3:
                task_id, channel, value = item
                normalized.append((task_id, channel, value))
                continue
            if len(item) == 4:
                task_id, _task_path, channel, value = item
                normalized.append((task_id, channel, value))
                continue

        # Defensive fallback: keep malformed legacy entries from crashing resume.
        # Use a synthetic channel so the data remains inspectable in telemetry/logs.
        normalized.append((None, "__malformed_pending_write__", item))
    return normalized


class RepositoryCheckpointSaver(BaseCheckpointSaver):
    """Checkpoint saver nativo para LangGraph usando os repositories do framework."""

    def __init__(self, settings, repository=None):
        self.settings = settings
        self.repository = repository or create_checkpoint_repository(settings)
        self._loop: asyncio.AbstractEventLoop | None = None

    def _run(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        # LangGraph may call sync methods from a worker thread; when already in
        # an event loop prefer a short-lived thread to avoid nested-loop errors.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: asyncio.run(coro)).result()

    def _make_tuple(self, payload: dict[str, Any] | None):
        if not payload:
            return None
        config = payload.get("config") or {"configurable": {"thread_id": payload.get("thread_id")}}
        checkpoint = payload.get("checkpoint") or {}
        metadata = payload.get("metadata") or {}
        parent_config = payload.get("parent_config")
        pending_writes = _normalize_pending_writes(payload.get("pending_writes") or [])
        try:
            from langgraph.checkpoint.base import CheckpointTuple
            return CheckpointTuple(config=config, checkpoint=checkpoint, metadata=metadata, parent_config=parent_config, pending_writes=pending_writes)
        except Exception:
            return {
                "config": config,
                "checkpoint": checkpoint,
                "metadata": metadata,
                "parent_config": parent_config,
                "pending_writes": pending_writes,
            }

    async def aget_tuple(self, config: dict[str, Any]):
        return self._make_tuple(await self.repository.get_latest(_thread_id(config)))

    def get_tuple(self, config: dict[str, Any]):
        return self._run(self.aget_tuple(config))

    async def aput(self, config: dict[str, Any], checkpoint: dict[str, Any], metadata: dict[str, Any] | None = None, new_versions: dict[str, Any] | None = None):
        thread_id = _thread_id(config)
        checkpoint_id = _checkpoint_id(checkpoint)
        next_config = {
            **(config or {}),
            "configurable": {
                **((config or {}).get("configurable") or {}),
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            },
        }
        await self.repository.put(thread_id, {
            "thread_id": thread_id,
            "config": _jsonable(next_config),
            "checkpoint": _jsonable(checkpoint),
            "metadata": _jsonable(metadata or {}),
            "new_versions": _jsonable(new_versions or {}),
            "checkpoint_id": checkpoint_id,
        })
        return next_config

    def put(self, config: dict[str, Any], checkpoint: dict[str, Any], metadata: dict[str, Any] | None = None, new_versions: dict[str, Any] | None = None):
        return self._run(self.aput(config, checkpoint, metadata, new_versions))

    async def aput_writes(self, config: dict[str, Any], writes: list[tuple[str, Any]], task_id: str, task_path: str = ""):
        thread_id = _thread_id(config)
        try:
            latest = await self.repository.get_latest(thread_id) or {"thread_id": thread_id, "config": config, "checkpoint": {}, "metadata": {}}
        except:
            latest = {
                "thread_id": thread_id,
                "config": config,
                "checkpoint": {},
                "metadata": {},
                "pending_writes": [],
            }

        pending = list(latest.get("pending_writes") or [])
        for channel, value in writes or []:
            pending.append({"task_id": task_id, "task_path": task_path, "channel": channel, "value": _jsonable(value)})
        latest["pending_writes"] = pending
        await self.repository.put(thread_id, latest)

    def put_writes(self, config: dict[str, Any], writes: list[tuple[str, Any]], task_id: str, task_path: str = ""):
        return self._run(self.aput_writes(config, writes, task_id, task_path))

    async def alist(self, config: dict[str, Any] | None = None, *, filter: dict[str, Any] | None = None, before: dict[str, Any] | None = None, limit: int | None = None) -> AsyncIterator[Any]:
        # Repository interface currently exposes only latest; this is enough for
        # resume/recovery. Oracle/SQLite repositories can later implement full list.
        if config is None:
            return
        item = await self.aget_tuple(config)
        if item:
            yield item

    def list(self, config: dict[str, Any] | None = None, *, filter: dict[str, Any] | None = None, before: dict[str, Any] | None = None, limit: int | None = None) -> Iterator[Any]:
        item = self.get_tuple(config or {}) if config else None
        if item:
            yield item


def create_langgraph_checkpointer(settings):
    """Factory used by applications when compiling LangGraph.

    By default the framework now returns RepositoryCheckpointSaver even for
    CHECKPOINT_REPOSITORY_PROVIDER=memory, because the repository wrapper adds
    integrity checks, retry, recovery and compaction.

    Set ENABLE_RESILIENT_CHECKPOINTER=false to fall back to LangGraph MemorySaver
    for very small local experiments.
    """
    provider = getattr(settings, "CHECKPOINT_REPOSITORY_PROVIDER", "memory")
    resilient = bool(getattr(settings, "ENABLE_RESILIENT_CHECKPOINTER", True))
    if provider == "memory" and not resilient:
        try:
            from langgraph.checkpoint.memory import MemorySaver
            return MemorySaver()
        except Exception:
            return RepositoryCheckpointSaver(settings)
    return RepositoryCheckpointSaver(settings)
