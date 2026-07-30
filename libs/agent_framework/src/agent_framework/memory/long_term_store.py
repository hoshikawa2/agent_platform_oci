from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, Sequence

from .long_term_models import LongTermMemoryItem, utc_now


class LongTermMemoryStore(Protocol):
    async def upsert_many(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        subject_key: str,
        items: Sequence[dict[str, Any]],
        source_session_id: str | None = None,
        source_message_id: str | None = None,
    ) -> list[LongTermMemoryItem]: ...

    async def search(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        subject_key: str,
        limit: int = 20,
    ) -> list[LongTermMemoryItem]: ...


class InMemoryLongTermMemoryStore:
    def __init__(self):
        self._items: dict[tuple[str, str, str, str, str], LongTermMemoryItem] = {}

    async def upsert_many(self, **kwargs):
        saved = []
        now = utc_now()
        for raw in kwargs["items"]:
            key = (
                kwargs["tenant_id"],
                kwargs["agent_id"],
                kwargs["subject_key"],
                str(raw.get("category") or "fact"),
                str(raw.get("key") or ""),
            )
            if not key[-1] or not raw.get("value"):
                continue
            old = self._items.get(key)
            item = LongTermMemoryItem(
                old.memory_id if old else str(uuid.uuid4()),
                key[0], key[1], key[2], key[3], key[4],
                str(raw["value"]),
                float(raw.get("confidence", 1.0)),
                kwargs.get("source_session_id"),
                kwargs.get("source_message_id"),
                old.created_at if old else now,
                now,
                dict(raw.get("metadata") or {}),
            )
            self._items[key] = item
            saved.append(item)
        return saved

    async def search(self, *, tenant_id, agent_id, subject_key, limit=20):
        values = [
            value for key, value in self._items.items()
            if key[:3] == (tenant_id, agent_id, subject_key)
        ]
        return sorted(
            values,
            key=lambda item: (item.confidence, item.updated_at),
            reverse=True,
        )[:limit]


class SQLiteLongTermMemoryStore:
    def __init__(
        self,
        path: str = "./data/agent_framework.db",
        table: str = "agentfw_long_term_memory",
    ):
        self.path = str(path)
        self.table = _validate_identifier(table, upper=False)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._ready = False
        self._lock = asyncio.Lock()

    def _connect(self):
        return sqlite3.connect(self.path)

    def _init_sync(self):
        sql = f"""CREATE TABLE IF NOT EXISTS {self.table} (
            memory_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, agent_id TEXT NOT NULL,
            subject_key TEXT NOT NULL, category TEXT NOT NULL, memory_key TEXT NOT NULL,
            memory_value TEXT NOT NULL, confidence REAL NOT NULL, source_session_id TEXT,
            source_message_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            metadata_json TEXT, UNIQUE(tenant_id,agent_id,subject_key,category,memory_key))"""
        with self._connect() as db:
            db.execute(sql)
            db.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.table}_subject "
                f"ON {self.table}(tenant_id,agent_id,subject_key,updated_at)"
            )

    async def _ensure(self):
        if self._ready:
            return
        async with self._lock:
            if not self._ready:
                await asyncio.to_thread(self._init_sync)
                self._ready = True

    def _upsert_sync(
        self, tenant_id, agent_id, subject_key, items,
        source_session_id, source_message_id,
    ):
        now = utc_now()
        saved = []
        with self._connect() as db:
            for raw in items:
                category = str(raw.get("category") or "fact").lower()
                key = str(raw.get("key") or "").lower()
                value = str(raw.get("value") or "").strip()
                if not key or not value:
                    continue
                row = db.execute(
                    f"SELECT memory_id,created_at FROM {self.table} "
                    "WHERE tenant_id=? AND agent_id=? AND subject_key=? "
                    "AND category=? AND memory_key=?",
                    (tenant_id, agent_id, subject_key, category, key),
                ).fetchone()
                memory_id = row[0] if row else str(uuid.uuid4())
                created_at = row[1] if row else now
                confidence = float(raw.get("confidence", 1.0))
                metadata = dict(raw.get("metadata") or {})
                db.execute(
                    f"""INSERT INTO {self.table}(
                        memory_id,tenant_id,agent_id,subject_key,category,memory_key,
                        memory_value,confidence,source_session_id,source_message_id,
                        created_at,updated_at,metadata_json)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(tenant_id,agent_id,subject_key,category,memory_key)
                    DO UPDATE SET memory_value=excluded.memory_value,
                        confidence=excluded.confidence,
                        source_session_id=excluded.source_session_id,
                        source_message_id=excluded.source_message_id,
                        updated_at=excluded.updated_at,
                        metadata_json=excluded.metadata_json""",
                    (
                        memory_id, tenant_id, agent_id, subject_key, category, key,
                        value, confidence, source_session_id, source_message_id,
                        created_at, now, json.dumps(metadata, ensure_ascii=False),
                    ),
                )
                saved.append(LongTermMemoryItem(
                    memory_id, tenant_id, agent_id, subject_key, category, key,
                    value, confidence, source_session_id, source_message_id,
                    created_at, now, metadata,
                ))
        return saved

    async def upsert_many(self, **kwargs):
        await self._ensure()
        return await asyncio.to_thread(
            self._upsert_sync,
            kwargs["tenant_id"], kwargs["agent_id"], kwargs["subject_key"],
            list(kwargs["items"]), kwargs.get("source_session_id"),
            kwargs.get("source_message_id"),
        )

    def _search_sync(self, tenant_id, agent_id, subject_key, limit):
        with self._connect() as db:
            rows = db.execute(
                f"SELECT memory_id,tenant_id,agent_id,subject_key,category,memory_key,"
                f"memory_value,confidence,source_session_id,source_message_id,"
                f"created_at,updated_at,metadata_json FROM {self.table} "
                "WHERE tenant_id=? AND agent_id=? AND subject_key=? "
                "ORDER BY confidence DESC,updated_at DESC LIMIT ?",
                (tenant_id, agent_id, subject_key, int(limit)),
            ).fetchall()
        return [
            LongTermMemoryItem(*row[:12], metadata=json.loads(row[12] or "{}"))
            for row in rows
        ]

    async def search(self, **kwargs):
        await self._ensure()
        return await asyncio.to_thread(
            self._search_sync,
            kwargs["tenant_id"], kwargs["agent_id"], kwargs["subject_key"],
            kwargs.get("limit", 20),
        )


def _validate_identifier(value: str, *, upper: bool = True) -> str:
    identifier = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_$#]{0,127}", identifier):
        raise ValueError(f"Invalid SQL identifier: {value!r}")
    return identifier.upper() if upper else identifier


def _as_iso(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def _load_json(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "read"):
        value = value.read()
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    try:
        loaded = json.loads(value)
        return loaded if isinstance(loaded, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


class OracleAutonomousLongTermMemoryStore:
    """Long-Term Memory provider for Oracle Autonomous Database.

    The implementation uses python-oracledb in thin mode and reuses the
    framework's ADB_* settings. Synchronous database operations run in worker
    threads so FastAPI/LangGraph's event loop is not blocked.
    """

    def __init__(self, settings):
        self.user = str(getattr(settings, "ADB_USER", "") or "")
        self.password = str(getattr(settings, "ADB_PASSWORD", "") or "")
        self.dsn = str(getattr(settings, "ADB_DSN", "") or "")
        self.wallet_location = getattr(settings, "ADB_WALLET_LOCATION", None)
        self.wallet_password = getattr(settings, "ADB_WALLET_PASSWORD", None)
        default_table = (
            f"{getattr(settings, 'ADB_TABLE_PREFIX', 'AGENTFW')}_LONG_TERM_MEMORY"
        )
        configured_table = (
            getattr(settings, "LONG_TERM_MEMORY_ORACLE_TABLE", None)
            or default_table
        )
        self.table = _validate_identifier(configured_table)
        self.index_name = _validate_identifier(f"IX_{self.table}_SUBJECT")
        self.constraint_name = _validate_identifier(f"UQ_{self.table}_FACT")
        self._ready = False
        self._lock = asyncio.Lock()
        if not self.user or not self.password or not self.dsn:
            raise RuntimeError(
                "ADB_USER, ADB_PASSWORD and ADB_DSN are required when "
                "LONG_TERM_MEMORY_PROVIDER is autonomous/oracle"
            )

    @contextmanager
    def _connect(self):
        try:
            import oracledb
        except ImportError as exc:
            raise RuntimeError(
                "python-oracledb is required for the Autonomous Long-Term "
                "Memory provider. Install it with: pip install oracledb"
            ) from exc

        oracledb.defaults.fetch_lobs = False
        kwargs: dict[str, Any] = {}
        if self.wallet_location:
            kwargs["config_dir"] = self.wallet_location
            kwargs["wallet_location"] = self.wallet_location
        if self.wallet_password:
            kwargs["wallet_password"] = self.wallet_password
        connection = oracledb.connect(
            user=self.user,
            password=self.password,
            dsn=self.dsn,
            **kwargs,
        )
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _ignore_already_exists(cursor, ddl: str) -> None:
        try:
            cursor.execute(ddl)
        except Exception as exc:
            message = str(exc)
            if "ORA-00955" in message or "ORA-01408" in message:
                return
            raise

    def _init_sync(self) -> None:
        with self._connect() as connection:
            cursor = connection.cursor()
            self._ignore_already_exists(cursor, f"""
                CREATE TABLE {self.table} (
                    MEMORY_ID VARCHAR2(36) PRIMARY KEY,
                    TENANT_ID VARCHAR2(128) NOT NULL,
                    AGENT_ID VARCHAR2(128) NOT NULL,
                    SUBJECT_KEY VARCHAR2(512) NOT NULL,
                    CATEGORY VARCHAR2(128) NOT NULL,
                    MEMORY_KEY VARCHAR2(256) NOT NULL,
                    MEMORY_VALUE CLOB NOT NULL,
                    CONFIDENCE NUMBER(5,4) DEFAULT 1 NOT NULL,
                    SOURCE_SESSION_ID VARCHAR2(512),
                    SOURCE_MESSAGE_ID VARCHAR2(256),
                    CREATED_AT TIMESTAMP WITH TIME ZONE NOT NULL,
                    UPDATED_AT TIMESTAMP WITH TIME ZONE NOT NULL,
                    METADATA_JSON CLOB CHECK (METADATA_JSON IS JSON),
                    CONSTRAINT {self.constraint_name} UNIQUE (
                        TENANT_ID, AGENT_ID, SUBJECT_KEY, CATEGORY, MEMORY_KEY
                    )
                )
            """)
            self._ignore_already_exists(cursor, f"""
                CREATE INDEX {self.index_name}
                ON {self.table} (
                    TENANT_ID, AGENT_ID, SUBJECT_KEY, UPDATED_AT DESC
                )
            """)

    async def _ensure(self) -> None:
        if self._ready:
            return
        async with self._lock:
            if not self._ready:
                await asyncio.to_thread(self._init_sync)
                self._ready = True

    def _find_existing(
        self, cursor, tenant_id: str, agent_id: str, subject_key: str,
        category: str, memory_key: str,
    ) -> tuple[str, Any] | None:
        cursor.execute(
            f"""SELECT MEMORY_ID, CREATED_AT FROM {self.table}
                WHERE TENANT_ID = :tenant_id
                  AND AGENT_ID = :agent_id
                  AND SUBJECT_KEY = :subject_key
                  AND CATEGORY = :category
                  AND MEMORY_KEY = :memory_key""",
            tenant_id=tenant_id,
            agent_id=agent_id,
            subject_key=subject_key,
            category=category,
            memory_key=memory_key,
        )
        return cursor.fetchone()

    def _upsert_sync(
        self, tenant_id: str, agent_id: str, subject_key: str,
        items: Sequence[dict[str, Any]], source_session_id: str | None,
        source_message_id: str | None,
    ) -> list[LongTermMemoryItem]:
        now = datetime.now(timezone.utc)
        saved: list[LongTermMemoryItem] = []
        with self._connect() as connection:
            cursor = connection.cursor()
            for raw in items:
                category = str(raw.get("category") or "fact").strip().lower()
                memory_key = str(raw.get("key") or "").strip().lower()
                value = str(raw.get("value") or "").strip()
                if not memory_key or not value:
                    continue

                existing = self._find_existing(
                    cursor, tenant_id, agent_id, subject_key,
                    category, memory_key,
                )
                memory_id = str(existing[0]) if existing else str(uuid.uuid4())
                created_at = existing[1] if existing else now
                confidence = float(raw.get("confidence", 1.0))
                metadata = dict(raw.get("metadata") or {})
                metadata_json = json.dumps(metadata, ensure_ascii=False, default=str)

                cursor.execute(f"""
                    MERGE INTO {self.table} target
                    USING (
                        SELECT
                            :tenant_id AS TENANT_ID,
                            :agent_id AS AGENT_ID,
                            :subject_key AS SUBJECT_KEY,
                            :category AS CATEGORY,
                            :memory_key AS MEMORY_KEY
                        FROM dual
                    ) source
                    ON (
                        target.TENANT_ID = source.TENANT_ID
                        AND target.AGENT_ID = source.AGENT_ID
                        AND target.SUBJECT_KEY = source.SUBJECT_KEY
                        AND target.CATEGORY = source.CATEGORY
                        AND target.MEMORY_KEY = source.MEMORY_KEY
                    )
                    WHEN MATCHED THEN UPDATE SET
                        target.MEMORY_VALUE = :memory_value,
                        target.CONFIDENCE = :confidence,
                        target.SOURCE_SESSION_ID = :source_session_id,
                        target.SOURCE_MESSAGE_ID = :source_message_id,
                        target.UPDATED_AT = :updated_at,
                        target.METADATA_JSON = :metadata_json
                    WHEN NOT MATCHED THEN INSERT (
                        MEMORY_ID, TENANT_ID, AGENT_ID, SUBJECT_KEY,
                        CATEGORY, MEMORY_KEY, MEMORY_VALUE, CONFIDENCE,
                        SOURCE_SESSION_ID, SOURCE_MESSAGE_ID,
                        CREATED_AT, UPDATED_AT, METADATA_JSON
                    ) VALUES (
                        :memory_id, :tenant_id, :agent_id, :subject_key,
                        :category, :memory_key, :memory_value, :confidence,
                        :source_session_id, :source_message_id,
                        :created_at, :updated_at, :metadata_json
                    )
                """, {
                    "memory_id": memory_id,
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "subject_key": subject_key,
                    "category": category,
                    "memory_key": memory_key,
                    "memory_value": value,
                    "confidence": confidence,
                    "source_session_id": source_session_id,
                    "source_message_id": source_message_id,
                    "created_at": created_at,
                    "updated_at": now,
                    "metadata_json": metadata_json,
                })
                saved.append(LongTermMemoryItem(
                    memory_id=memory_id,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    subject_key=subject_key,
                    category=category,
                    key=memory_key,
                    value=value,
                    confidence=confidence,
                    source_session_id=source_session_id,
                    source_message_id=source_message_id,
                    created_at=_as_iso(created_at),
                    updated_at=_as_iso(now),
                    metadata=metadata,
                ))
        return saved

    async def upsert_many(self, **kwargs):
        await self._ensure()
        return await asyncio.to_thread(
            self._upsert_sync,
            kwargs["tenant_id"],
            kwargs["agent_id"],
            kwargs["subject_key"],
            list(kwargs["items"]),
            kwargs.get("source_session_id"),
            kwargs.get("source_message_id"),
        )

    def _search_sync(
        self, tenant_id: str, agent_id: str, subject_key: str, limit: int,
    ) -> list[LongTermMemoryItem]:
        safe_limit = max(1, min(int(limit), 500))
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(f"""
                SELECT
                    MEMORY_ID, TENANT_ID, AGENT_ID, SUBJECT_KEY,
                    CATEGORY, MEMORY_KEY, MEMORY_VALUE, CONFIDENCE,
                    SOURCE_SESSION_ID, SOURCE_MESSAGE_ID,
                    CREATED_AT, UPDATED_AT, METADATA_JSON
                FROM {self.table}
                WHERE TENANT_ID = :tenant_id
                  AND AGENT_ID = :agent_id
                  AND SUBJECT_KEY = :subject_key
                ORDER BY CONFIDENCE DESC, UPDATED_AT DESC
                FETCH FIRST {safe_limit} ROWS ONLY
            """, {
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "subject_key": subject_key,
            })
            rows = cursor.fetchall()

        result: list[LongTermMemoryItem] = []
        for row in rows:
            result.append(LongTermMemoryItem(
                memory_id=str(row[0]),
                tenant_id=str(row[1]),
                agent_id=str(row[2]),
                subject_key=str(row[3]),
                category=str(row[4]),
                key=str(row[5]),
                value=str(row[6]),
                confidence=float(row[7]),
                source_session_id=str(row[8]) if row[8] is not None else None,
                source_message_id=str(row[9]) if row[9] is not None else None,
                created_at=_as_iso(row[10]),
                updated_at=_as_iso(row[11]),
                metadata=_load_json(row[12]),
            ))
        return result

    async def search(self, **kwargs):
        await self._ensure()
        return await asyncio.to_thread(
            self._search_sync,
            kwargs["tenant_id"],
            kwargs["agent_id"],
            kwargs["subject_key"],
            kwargs.get("limit", 20),
        )


AutonomousLongTermMemoryStore = OracleAutonomousLongTermMemoryStore


def create_long_term_memory_store(settings):
    provider = str(
        getattr(settings, "LONG_TERM_MEMORY_PROVIDER", "sqlite")
    ).strip().lower()
    if provider == "memory":
        return InMemoryLongTermMemoryStore()
    if provider in {"autonomous", "oracle"}:
        return OracleAutonomousLongTermMemoryStore(settings)
    if provider != "sqlite":
        raise ValueError(
            "Unsupported LONG_TERM_MEMORY_PROVIDER: "
            f"{provider!r}. Expected memory, sqlite, autonomous or oracle."
        )
    path = (
        getattr(settings, "LONG_TERM_MEMORY_SQLITE_PATH", None)
        or getattr(settings, "SQLITE_DB_PATH", "./data/agent_framework.db")
    )
    return SQLiteLongTermMemoryStore(
        path,
        getattr(settings, "LONG_TERM_MEMORY_TABLE", "agentfw_long_term_memory"),
    )
