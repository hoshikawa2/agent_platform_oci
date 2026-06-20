from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from agent_framework.persistence.sqlite_store import SQLiteStore

logger = logging.getLogger("agent_framework.checkpoints")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _json_loads(value: str | bytes | None, default: Any):
    if value is None:
        return default
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    try:
        return json.loads(value)
    except Exception:
        return default


def _sha256(value: Any) -> str:
    return hashlib.sha256(_json_dumps(value).encode("utf-8")).hexdigest()


class CheckpointIntegrityError(RuntimeError):
    """Raised when a persisted checkpoint envelope fails checksum validation."""


class CheckpointRecoveryError(RuntimeError):
    """Raised when recovery cannot find a valid checkpoint."""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.05
    max_delay_seconds: float = 1.0
    jitter_seconds: float = 0.05


class CheckpointIntegrityService:
    """Creates and validates immutable checkpoint envelopes.

    The repository stores an envelope instead of only the raw LangGraph payload:
    - schema_version: enables future migrations;
    - payload_hash: SHA-256 over the payload;
    - envelope_id: idempotency/correlation id;
    - compacted: marks synthetic compacted snapshots.
    """

    SCHEMA_VERSION = 1
    ENVELOPE_MARKER = "agent_framework_checkpoint_envelope"

    def wrap(self, thread_id: str, checkpoint: dict[str, Any], *, compacted: bool = False) -> dict[str, Any]:
        payload = checkpoint or {}
        return {
            "_type": self.ENVELOPE_MARKER,
            "schema_version": self.SCHEMA_VERSION,
            "envelope_id": str(uuid.uuid4()),
            "thread_id": thread_id,
            "checkpoint_id": str(payload.get("checkpoint_id") or (payload.get("checkpoint") or {}).get("id") or uuid.uuid4()),
            "payload_hash": _sha256(payload),
            "payload": payload,
            "compacted": bool(compacted),
            "created_at": _utc_now(),
        }

    def is_envelope(self, value: dict[str, Any] | None) -> bool:
        return isinstance(value, dict) and value.get("_type") == self.ENVELOPE_MARKER

    def unwrap(self, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        if not self.is_envelope(value):
            # Backwards compatibility with old checkpoints from previous project versions.
            return value
        expected = value.get("payload_hash")
        payload = value.get("payload") or {}
        actual = _sha256(payload)
        if expected != actual:
            raise CheckpointIntegrityError(
                f"Checkpoint corrompido para thread_id={value.get('thread_id')}: hash esperado={expected}, hash atual={actual}"
            )
        if int(value.get("schema_version") or 0) > self.SCHEMA_VERSION:
            raise CheckpointIntegrityError(
                f"Checkpoint usa schema_version={value.get('schema_version')} maior que o suportado={self.SCHEMA_VERSION}"
            )
        return payload


class LangGraphCheckpointRepository(ABC):
    @abstractmethod
    async def put(self, thread_id: str, checkpoint: dict[str, Any]) -> None: ...

    @abstractmethod
    async def get_latest(self, thread_id: str) -> dict[str, Any] | None: ...

    async def list_latest(self, thread_id: str, limit: int = 20) -> list[dict[str, Any]]:
        latest = await self.get_latest(thread_id)
        return [latest] if latest else []

    async def compact(self, thread_id: str, keep_last: int = 20) -> int:
        return 0

    @staticmethod
    def is_valid_checkpoint(checkpoint):
        if not isinstance(checkpoint, dict):
            return False
        if "v" in checkpoint:
            return True
        if (
                "checkpoint" in checkpoint
                and isinstance(checkpoint["checkpoint"], dict)
                and "v" in checkpoint["checkpoint"]
        ):
            return True
        return False

class InMemoryCheckpointRepository(LangGraphCheckpointRepository):
    def __init__(self):
        self._data: dict[str, list[dict[str, Any]]] = {}

    async def put(self, thread_id: str, checkpoint: dict[str, Any]):
        self._data.setdefault(thread_id, []).append(checkpoint)

    async def get_latest(self, thread_id: str):
        items = self._data.get(thread_id, [])
        return items[-1] if items else None

    async def list_latest(self, thread_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return list(reversed(self._data.get(thread_id, [])[-limit:]))

    async def compact(self, thread_id: str, keep_last: int = 20) -> int:
        items = self._data.get(thread_id, [])
        if len(items) <= keep_last:
            return 0
        removed = len(items) - keep_last
        self._data[thread_id] = items[-keep_last:]
        return removed


class SQLiteCheckpointRepository(LangGraphCheckpointRepository):
    def __init__(self, settings):
        self.store = SQLiteStore(settings.SQLITE_DB_PATH)

    async def put(self, thread_id: str, checkpoint: dict[str, Any]):
        await asyncio.to_thread(self.store.put_checkpoint, thread_id, checkpoint)

    async def get_latest(self, thread_id: str):
        return await asyncio.to_thread(self.store.get_latest_checkpoint, thread_id)

    async def list_latest(self, thread_id: str, limit: int = 20) -> list[dict[str, Any]]:
        def _list():
            with self.store.connect() as con:
                rows = con.execute(
                    "select checkpoint_json from workflow_checkpoints where thread_id=? order by id desc limit ?",
                    (thread_id, int(limit)),
                ).fetchall()
            return [_json_loads(r["checkpoint_json"], None) for r in rows if r]

        return await asyncio.to_thread(_list)

    async def compact(self, thread_id: str, keep_last: int = 20) -> int:
        def _compact():
            with self.store.connect() as con:
                rows = con.execute(
                    "select id from workflow_checkpoints where thread_id=? order by id desc",
                    (thread_id,),
                ).fetchall()
                ids = [int(r["id"]) for r in rows]
                delete_ids = ids[int(keep_last):]
                if not delete_ids:
                    return 0
                con.executemany("delete from workflow_checkpoints where id=?", [(i,) for i in delete_ids])
                return len(delete_ids)

        return await asyncio.to_thread(_compact)


class OracleCheckpointRepository(LangGraphCheckpointRepository):
    """Checkpoint repository real para Oracle/Autonomous Database.

    O OracleStore já cria as tabelas FIRST-compatible. A compactação é best-effort:
    remove checkpoints antigos quando o store expõe conexão e prefixo de tabelas.
    """

    def __init__(self, settings):
        from agent_framework.persistence.oracle_store import OracleStore

        self.store = OracleStore(settings)

    async def put(self, thread_id: str, checkpoint: dict[str, Any]):
        await self.store.put_checkpoint(thread_id, checkpoint)

    async def get_latest(self, thread_id: str):
        return await self.store.get_latest_checkpoint(thread_id)

    async def list_latest(self, thread_id: str, limit: int = 20) -> list[dict[str, Any]]:
        if not hasattr(self.store, "connect") or not hasattr(self.store, "t"):
            return await super().list_latest(thread_id, limit)

        def _list():
            sql = f"""
                select CHECKPOINT_JSON
                from {self.store.t('WORKFLOW_CHECKPOINT')}
                where THREAD_ID = :thread_id
                order by ID desc
                fetch first :limit rows only
            """
            with self.store.connect() as conn:
                rows = conn.cursor().execute(sql, dict(thread_id=thread_id, limit=int(limit))).fetchall()
            return [_json_loads(r[0], None) for r in rows if r]

        return await asyncio.to_thread(_list)

    async def compact(self, thread_id: str, keep_last: int = 20) -> int:
        if not hasattr(self.store, "connect") or not hasattr(self.store, "t"):
            return 0

        def _compact():
            table = self.store.t("WORKFLOW_CHECKPOINT")
            sql_count = f"select count(*) from {table} where THREAD_ID = :thread_id"
            sql_delete = f"""
                delete from {table}
                where THREAD_ID = :thread_id
                  and ID not in (
                    select ID from {table}
                    where THREAD_ID = :thread_id
                    order by ID desc
                    fetch first :keep_last rows only
                  )
            """
            with self.store.connect() as conn:
                cur = conn.cursor()
                before = int(cur.execute(sql_count, dict(thread_id=thread_id)).fetchone()[0])
                cur.execute(sql_delete, dict(thread_id=thread_id, keep_last=int(keep_last)))
                after = int(cur.execute(sql_count, dict(thread_id=thread_id)).fetchone()[0])
                return max(0, before - after)

        return await asyncio.to_thread(_compact)


AutonomousCheckpointRepository = OracleCheckpointRepository


class ResilientCheckpointRepository(LangGraphCheckpointRepository):
    """Adds integrity, retry, compaction and recovery to any repository.

    This wrapper is intentionally repository-neutral. It can protect memory,
    SQLite and Oracle repositories without changing LangGraph code.
    """

    def __init__(
        self,
        inner: LangGraphCheckpointRepository,
        *,
        integrity: CheckpointIntegrityService | None = None,
        retry_policy: RetryPolicy | None = None,
        enable_integrity: bool = True,
        enable_compaction: bool = True,
        compact_every: int = 50,
        keep_last: int = 20,
        recovery_scan_limit: int = 25,
    ):
        self.inner = inner
        self.integrity = integrity or CheckpointIntegrityService()
        self.retry_policy = retry_policy or RetryPolicy()
        self.enable_integrity = enable_integrity
        self.enable_compaction = enable_compaction
        self.compact_every = max(1, int(compact_every))
        self.keep_last = max(1, int(keep_last))
        self.recovery_scan_limit = max(1, int(recovery_scan_limit))
        self._put_count_by_thread: dict[str, int] = {}

    async def _with_retry(self, operation_name: str, coro_factory):
        last_exc: Exception | None = None
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            try:
                return await coro_factory()
            except Exception as exc:  # noqa: BLE001 - repository failures vary by backend
                last_exc = exc
                if attempt >= self.retry_policy.max_attempts:
                    break
                delay = min(
                    self.retry_policy.max_delay_seconds,
                    self.retry_policy.base_delay_seconds * (2 ** (attempt - 1)),
                ) + random.uniform(0, self.retry_policy.jitter_seconds)
                logger.warning("checkpoint.%s.retry attempt=%s delay=%.3fs error=%s", operation_name, attempt, delay, exc)
                await asyncio.sleep(delay)
        raise last_exc  # type: ignore[misc]

    async def put(self, thread_id: str, checkpoint: dict[str, Any]) -> None:
        payload = self.integrity.wrap(thread_id, checkpoint) if self.enable_integrity else checkpoint
        await self._with_retry("put", lambda: self.inner.put(thread_id, payload))
        self._put_count_by_thread[thread_id] = self._put_count_by_thread.get(thread_id, 0) + 1
        if self.enable_compaction and self._put_count_by_thread[thread_id] % self.compact_every == 0:
            try:
                removed = await self.inner.compact(thread_id, keep_last=self.keep_last)
                if removed:
                    logger.info("checkpoint.compaction thread_id=%s removed=%s keep_last=%s", thread_id, removed, self.keep_last)
            except Exception as exc:  # compaction must never break the user flow
                logger.warning("checkpoint.compaction.failed thread_id=%s error=%s", thread_id, exc)

    async def get_latest(self, thread_id: str) -> dict[str, Any] | None:
        return await self.recover_latest(thread_id)

    async def list_latest(self, thread_id: str, limit: int = 20) -> list[dict[str, Any]]:
        raw_items = await self.inner.list_latest(thread_id, limit)
        out: list[dict[str, Any]] = []
        for item in raw_items:
            try:
                payload = self.integrity.unwrap(item) if self.enable_integrity else item
                if payload is not None:
                    out.append(payload)
            except CheckpointIntegrityError:
                continue
        return out

    async def compact(self, thread_id: str, keep_last: int = 20) -> int:
        return await self.inner.compact(thread_id, keep_last=keep_last)

    async def recover_latest(self, thread_id: str) -> dict[str, Any] | None:
        """Return the newest valid LangGraph checkpoint, skipping corrupt or legacy records."""
        raw_items = await self._with_retry(
            "list_latest",
            lambda: self.inner.list_latest(thread_id, self.recovery_scan_limit),
        )

        first_integrity_error: Exception | None = None
        invalid_count = 0

        for raw in raw_items:
            try:
                payload = self.integrity.unwrap(raw)

                candidate = payload

                if (
                        isinstance(payload, dict)
                        and "checkpoint" in payload
                ):
                    candidate = payload["checkpoint"]

                if not self.is_valid_checkpoint(candidate):
                    continue

                return payload

            except CheckpointIntegrityError as exc:
                first_integrity_error = first_integrity_error or exc
                logger.error(
                    "checkpoint.recovery.skip_corrupt thread_id=%s error=%s",
                    thread_id,
                    exc,
                )
                continue

        if first_integrity_error:
            raise CheckpointRecoveryError(
                f"Nenhum checkpoint válido encontrado para thread_id={thread_id}"
            ) from first_integrity_error

        if invalid_count:
            logger.warning(
                "checkpoint.recovery.no_valid_langgraph_checkpoint "
                "thread_id=%s invalid_count=%s",
                thread_id,
                invalid_count,
            )

        return None

def _retry_policy_from_settings(settings) -> RetryPolicy:
    return RetryPolicy(
        max_attempts=int(getattr(settings, "CHECKPOINT_RETRY_MAX_ATTEMPTS", 3) or 3),
        base_delay_seconds=float(getattr(settings, "CHECKPOINT_RETRY_BASE_DELAY_SECONDS", 0.05) or 0.05),
        max_delay_seconds=float(getattr(settings, "CHECKPOINT_RETRY_MAX_DELAY_SECONDS", 1.0) or 1.0),
        jitter_seconds=float(getattr(settings, "CHECKPOINT_RETRY_JITTER_SECONDS", 0.05) or 0.05),
    )


def create_raw_checkpoint_repository(settings):
    provider = getattr(settings, "CHECKPOINT_REPOSITORY_PROVIDER", "memory")
    if provider == "sqlite":
        return SQLiteCheckpointRepository(settings)
    if provider in {"autonomous", "oracle"}:
        return OracleCheckpointRepository(settings)
    return InMemoryCheckpointRepository()


def create_checkpoint_repository(settings):
    raw = create_raw_checkpoint_repository(settings)
    if not bool(getattr(settings, "ENABLE_RESILIENT_CHECKPOINTER", True)):
        return raw
    return ResilientCheckpointRepository(
        raw,
        retry_policy=_retry_policy_from_settings(settings),
        enable_integrity=bool(getattr(settings, "ENABLE_CHECKPOINT_INTEGRITY", True)),
        enable_compaction=bool(getattr(settings, "ENABLE_CHECKPOINT_COMPACTION", True)),
        compact_every=int(getattr(settings, "CHECKPOINT_COMPACT_EVERY", 50) or 50),
        keep_last=int(getattr(settings, "CHECKPOINT_KEEP_LAST", 20) or 20),
        recovery_scan_limit=int(getattr(settings, "CHECKPOINT_RECOVERY_SCAN_LIMIT", 25) or 25),
    )
