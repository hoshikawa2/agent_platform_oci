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


def _parse_legacy_json_container(value: Any, expected: type) -> Any:
    """Recover containers that older JSON backends persisted as JSON strings.

    This is intentionally field-scoped: ordinary business strings must stay
    strings, even if their text happens to look like JSON.
    """
    current = value
    for _ in range(3):
        if isinstance(current, expected):
            return current
        if not isinstance(current, str):
            break
        text = current.strip()
        if not text:
            break
        if expected is dict and not text.startswith("{"):
            break
        if expected is list and not text.startswith("["):
            break
        try:
            current = json.loads(text)
        except Exception:
            break
    return current if isinstance(current, expected) else expected()


def _strict_json_value(value: Any, *, path: str = "$") -> Any:
    """Convert to repository-safe JSON without ever falling back to ``str``.

    ``default=str`` is unsafe for LangGraph checkpoints: runtime/task objects can
    become ordinary strings and later be consumed as typed values by Pregel.
    Keep native JSON containers recursively and fail loudly for an unsupported
    object instead of corrupting it silently.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): _strict_json_value(item, path=f"{path}.{key}")
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            _strict_json_value(item, path=f"{path}[{idx}]")
            for idx, item in enumerate(value)
        ]
    # Common durable scalar types that JSON does not know natively.
    if isinstance(value, uuid.UUID):
        return str(value)
    try:
        from datetime import date, datetime
        if isinstance(value, (date, datetime)):
            return value.isoformat()
    except Exception:
        pass
    try:
        from enum import Enum
        if isinstance(value, Enum):
            return _strict_json_value(value.value, path=path)
    except Exception:
        pass
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return _strict_json_value(value.model_dump(), path=path)
    raise TypeError(
        f"Checkpoint contém valor não serializável em {path}: "
        f"{type(value).__module__}.{type(value).__qualname__}"
    )


def _normalize_checkpoint(checkpoint: Any) -> dict[str, Any]:
    checkpoint = _parse_legacy_json_container(checkpoint, dict)
    if not isinstance(checkpoint, dict):
        return {}
    out = dict(checkpoint)
    out["channel_values"] = _parse_legacy_json_container(out.get("channel_values"), dict)
    out["channel_versions"] = _parse_legacy_json_container(out.get("channel_versions"), dict)
    raw_seen = _parse_legacy_json_container(out.get("versions_seen"), dict)
    out["versions_seen"] = {
        str(node): _parse_legacy_json_container(versions, dict)
        for node, versions in raw_seen.items()
    }
    if "pending_sends" in out:
        out["pending_sends"] = _parse_legacy_json_container(out.get("pending_sends"), list)
    if "updated_channels" in out and isinstance(out.get("updated_channels"), str):
        out["updated_channels"] = _parse_legacy_json_container(out.get("updated_channels"), list)
    return out


def _normalize_metadata(metadata: Any) -> dict[str, Any]:
    value = _parse_legacy_json_container(metadata, dict)
    return value if isinstance(value, dict) else {}


def _normalize_config(config: Any) -> dict[str, Any]:
    value = _parse_legacy_json_container(config, dict)
    if not isinstance(value, dict):
        return {}
    out = dict(value)
    out["configurable"] = _parse_legacy_json_container(out.get("configurable"), dict)
    return out


_EPHEMERAL_RUNTIME_KEYS = {"__pregel_runtime", "__pregel_store"}


def _strip_runtime_refs(value: Any) -> Any:
    """Recursively remove process-local runtime/store references only.

    Checkpoints may legitimately contain LangGraph internal channels whose names
    also start with ``__pregel_`` (for example task channels). Those are durable
    graph state and must be preserved. The corruption that triggers
    ``str.override`` is specifically a runtime/store object captured inside a
    nested RunnableConfig and later stringified by the JSON repository.
    """
    if isinstance(value, dict):
        return {
            key: _strip_runtime_refs(item)
            for key, item in value.items()
            if str(key) not in _EPHEMERAL_RUNTIME_KEYS
        }
    if isinstance(value, list):
        return [_strip_runtime_refs(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_strip_runtime_refs(item) for item in value)
    return value


def _durable_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Return a checkpoint-safe copy of a LangGraph RunnableConfig.

    LangGraph injects ephemeral private values such as ``__pregel_runtime`` and
    ``__pregel_store`` under ``configurable`` while a graph is running. They are
    process-local and must never cross the durable checkpoint boundary.

    The scrub is recursive because task/pending-write config fragments may be
    nested below regular config fields in newer LangGraph versions.
    """
    if not isinstance(config, dict):
        return {}
    cleaned = _strip_runtime_refs(config)
    if not isinstance(cleaned, dict):
        return {}
    configurable = cleaned.get("configurable")
    if isinstance(configurable, dict):
        cleaned = dict(cleaned)
        cleaned["configurable"] = {
            key: value
            for key, value in configurable.items()
            if not str(key).startswith("__pregel_")
        }
    return cleaned


def _canonical_checkpoint_config(
    payload: dict[str, Any],
    request_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rebuild the RunnableConfig returned to LangGraph from durable IDs only.

    Official LangGraph savers do not re-bind the full config that happened to be
    present when a checkpoint was written. They reconstruct a fresh config from
    ``thread_id``, ``checkpoint_ns`` and ``checkpoint_id``. Doing the same here
    prevents a historical/factory-time runtime value from being rebound into a
    new execution while remaining backward compatible with existing rows.
    """
    requested = _durable_config(request_config)
    stored = _durable_config(_normalize_config(payload.get("config")) if isinstance(payload, dict) else None)
    req_cfg = requested.get("configurable") if isinstance(requested.get("configurable"), dict) else {}
    stored_cfg = stored.get("configurable") if isinstance(stored.get("configurable"), dict) else {}
    checkpoint = payload.get("checkpoint") if isinstance(payload, dict) else {}
    checkpoint = checkpoint if isinstance(checkpoint, dict) else {}

    thread_id = (
        req_cfg.get("thread_id")
        or stored_cfg.get("thread_id")
        or payload.get("thread_id")
        or "default"
    )
    checkpoint_ns = req_cfg.get("checkpoint_ns")
    if checkpoint_ns is None:
        checkpoint_ns = stored_cfg.get("checkpoint_ns", "")

    requested_checkpoint_id = req_cfg.get("checkpoint_id")
    checkpoint_id = (
        requested_checkpoint_id
        or payload.get("checkpoint_id")
        or checkpoint.get("id")
        or stored_cfg.get("checkpoint_id")
    )

    configurable: dict[str, Any] = {
        "thread_id": str(thread_id),
        "checkpoint_ns": str(checkpoint_ns or ""),
    }
    if checkpoint_id not in (None, ""):
        configurable["checkpoint_id"] = str(checkpoint_id)
    return {"configurable": configurable}


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
        super().__init__()
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

    def _make_tuple(
        self,
        payload: dict[str, Any] | None,
        request_config: dict[str, Any] | None = None,
    ):
        if not payload:
            return None
        # Second-stage protection: never re-bind the full persisted RunnableConfig.
        # Rebuild only the durable identifiers, as official LangGraph savers do.
        config = _canonical_checkpoint_config(payload, request_config)
        checkpoint = _strip_runtime_refs(_normalize_checkpoint(payload.get("checkpoint") or {}))
        metadata = _strip_runtime_refs(_normalize_metadata(payload.get("metadata") or {}))
        raw_parent_config = payload.get("parent_config")
        if isinstance(raw_parent_config, dict):
            parent_payload = {
                "thread_id": payload.get("thread_id"),
                "config": raw_parent_config,
                "checkpoint_id": (raw_parent_config.get("configurable") or {}).get("checkpoint_id")
                if isinstance(raw_parent_config.get("configurable"), dict)
                else None,
                "checkpoint": {},
            }
            parent_config = _canonical_checkpoint_config(parent_payload)
        else:
            parent_config = None
        pending_writes = _normalize_pending_writes(
            _strip_runtime_refs(payload.get("pending_writes") or [])
        )
        try:
            from langgraph.checkpoint.base import CheckpointTuple
            return CheckpointTuple(config=config, checkpoint=checkpoint, metadata=metadata, parent_config=parent_config, pending_writes=pending_writes)
        except Exception:
            return {
                "config": _durable_config(config),
                "checkpoint": checkpoint,
                "metadata": metadata,
                "parent_config": parent_config,
                "pending_writes": pending_writes,
            }

    async def aget_tuple(self, config: dict[str, Any]):
        return self._make_tuple(
            await self.repository.get_latest(_thread_id(config)),
            request_config=config,
        )

    def get_tuple(self, config: dict[str, Any]):
        return self._run(self.aget_tuple(config))

    async def aput(self, config: dict[str, Any], checkpoint: dict[str, Any], metadata: dict[str, Any] | None = None, new_versions: dict[str, Any] | None = None):
        thread_id = _thread_id(config)
        checkpoint_id = _checkpoint_id(checkpoint)
        clean_config = _durable_config(config)
        clean_cfg = clean_config.get("configurable") if isinstance(clean_config.get("configurable"), dict) else {}
        checkpoint_ns = str(clean_cfg.get("checkpoint_ns") or "")
        # Return a fresh canonical config. Never feed process-local/factory-time
        # configurable values back into the next LangGraph super-step.
        next_config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }
        await self.repository.put(thread_id, {
            "thread_id": thread_id,
            "config": _strict_json_value(next_config, path="$.config"),
            "checkpoint": _strict_json_value(_strip_runtime_refs(_normalize_checkpoint(checkpoint)), path="$.checkpoint"),
            "metadata": _strict_json_value(_strip_runtime_refs(_normalize_metadata(metadata or {})), path="$.metadata"),
            "new_versions": _strict_json_value(_strip_runtime_refs(new_versions or {}), path="$.new_versions"),
            "checkpoint_id": checkpoint_id,
        })
        return next_config

    def put(self, config: dict[str, Any], checkpoint: dict[str, Any], metadata: dict[str, Any] | None = None, new_versions: dict[str, Any] | None = None):
        return self._run(self.aput(config, checkpoint, metadata, new_versions))

    async def aput_writes(self, config: dict[str, Any], writes: list[tuple[str, Any]], task_id: str, task_path: str = ""):
        thread_id = _thread_id(config)
        try:
            latest = await self.repository.get_latest(thread_id) or {"thread_id": thread_id, "config": _durable_config(config), "checkpoint": {}, "metadata": {}}
        except:
            latest = {
                "thread_id": thread_id,
                "config": _durable_config(config),
                "checkpoint": {},
                "metadata": {},
                "pending_writes": [],
            }

        if isinstance(latest, dict):
            # Do not keep extending a persisted RunnableConfig across super-steps.
            # Rebuild the same canonical config that aget_tuple() will expose.
            latest["config"] = _canonical_checkpoint_config(latest, config)
            if isinstance(latest.get("checkpoint"), dict):
                latest["checkpoint"] = _strip_runtime_refs(latest.get("checkpoint"))
            if isinstance(latest.get("metadata"), dict):
                latest["metadata"] = _strip_runtime_refs(latest.get("metadata"))
            if isinstance(latest.get("parent_config"), dict):
                parent_payload = {
                    "thread_id": latest.get("thread_id") or thread_id,
                    "config": latest.get("parent_config"),
                    "checkpoint_id": (latest.get("parent_config", {}).get("configurable") or {}).get("checkpoint_id")
                    if isinstance(latest.get("parent_config", {}).get("configurable"), dict)
                    else None,
                    "checkpoint": {},
                }
                latest["parent_config"] = _canonical_checkpoint_config(parent_payload)

        pending = list(latest.get("pending_writes") or [])
        for channel, value in writes or []:
            # Writes may contain nested task/RunnableConfig fragments. Scrub the
            # private runtime before the repository's JSON ``default=str`` layer.
            durable_value = _strip_runtime_refs(value)
            pending.append({
                "task_id": task_id,
                "task_path": task_path,
                "channel": channel,
                "value": _strict_json_value(durable_value, path=f"$.pending_writes[{task_id}].{channel}"),
            })
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
