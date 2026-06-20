from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def _json_dumps(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, default=str)


def _json_loads(value: str | bytes | None, default: Any):
    if value is None:
        return default
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    try:
        return json.loads(value)
    except Exception:
        return default


@dataclass
class OracleSettings:
    user: str
    password: str
    dsn: str
    wallet_location: str | None = None
    wallet_password: str | None = None
    table_prefix: str = "AGENTFW"


class OracleStore:
    """Oracle Autonomous Database store following the Agent Framework pattern.

    Uses direct oracledb.connect() with wallet arguments. Synchronous DB calls are
    exposed through asyncio.to_thread(), matching the main framework style.
    """

    def __init__(self, settings, auto_init_schema: bool = False):
        self.settings = settings
        self.cfg = OracleSettings(
            user=settings.ADB_USER or "",
            password=settings.ADB_PASSWORD or "",
            dsn=settings.ADB_DSN or "",
            wallet_location=getattr(settings, "ADB_WALLET_LOCATION", None),
            wallet_password=getattr(settings, "ADB_WALLET_PASSWORD", None),
            table_prefix=(getattr(settings, "ADB_TABLE_PREFIX", "AGENTFW") or "AGENTFW").upper().rstrip("_"),
        )
        if not self.cfg.user or not self.cfg.password or not self.cfg.dsn:
            raise RuntimeError("ADB_USER, ADB_PASSWORD and ADB_DSN are required")
        if auto_init_schema:
            self._init_schema()

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    def t(self, name: str) -> str:
        return f"{self.cfg.table_prefix}_{name}".upper()

    @contextmanager
    def connect(self):
        import oracledb
        oracledb.defaults.fetch_lobs = False
        kwargs = {}
        if self.cfg.wallet_location:
            kwargs["config_dir"] = self.cfg.wallet_location
            kwargs["wallet_location"] = self.cfg.wallet_location
        if self.cfg.wallet_password:
            kwargs["wallet_password"] = self.cfg.wallet_password
        conn = oracledb.connect(user=self.cfg.user, password=self.cfg.password, dsn=self.cfg.dsn, **kwargs)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    async def to_thread(self, func, *args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)

    def _exec_ddl_ignore_exists(self, cur, ddl: str):
        try:
            cur.execute(ddl)
        except Exception as exc:
            msg = str(exc)
            if "ORA-00955" in msg or "ORA-01408" in msg or "ORA-02275" in msg:
                return
            raise

    def _column_exists(self, cur, table_name: str, column_name: str) -> bool:
        cur.execute("""
            select count(*)
              from user_tab_columns
             where table_name = :table_name
               and column_name = :column_name
        """, {"table_name": self.t(table_name), "column_name": column_name.upper()})
        return int(cur.fetchone()[0] or 0) > 0

    def _ensure_column(self, cur, table_name: str, column_name: str, ddl_type: str):
        if not self._column_exists(cur, table_name, column_name):
            cur.execute(f"alter table {self.t(table_name)} add {column_name.upper()} {ddl_type}")

    def drop_schema(self):
        tables = [
            "EVALUATION_RESULT",
            "EVALUATION_FINDING",
            "EVALUATION_METRIC",
            "EVALUATION_ITEM",
            "EVALUATION_PROGRESS_EVENT",
            "EVALUATION_RUN",
        ]
        with self.connect() as conn:
            cur = conn.cursor()
            for table in tables:
                try:
                    cur.execute(f"drop table {self.t(table)} cascade constraints purge")
                except Exception as exc:
                    if "ORA-00942" in str(exc):
                        continue
                    raise

    def _init_schema(self):
        with self.connect() as conn:
            cur = conn.cursor()

            self._exec_ddl_ignore_exists(cur, f"""
                create table {self.t('EVALUATION_RUN')} (
                    RUN_ID varchar2(64) primary key,
                    AGENT_ID varchar2(128),
                    SOURCE varchar2(64),
                    PERIOD_START timestamp with time zone,
                    PERIOD_END timestamp with time zone,
                    STATUS varchar2(32) not null,
                    TOTAL_ITEMS number default 0 not null,
                    PROCESSED_ITEMS number default 0 not null,
                    FAILED_ITEMS number default 0 not null,
                    RETRY_COUNT number default 0 not null,
                    ERROR_MESSAGE clob,
                    LAST_HEARTBEAT_AT timestamp with time zone,
                    CREATED_AT timestamp with time zone not null,
                    UPDATED_AT timestamp with time zone not null
                )
            """)

            self._exec_ddl_ignore_exists(cur, f"""
                create table {self.t('EVALUATION_PROGRESS_EVENT')} (
                    ID number generated always as identity primary key,
                    RUN_ID varchar2(64) not null,
                    STAGE varchar2(128) not null,
                    MESSAGE varchar2(1000),
                    DETAILS_JSON clob check (DETAILS_JSON is json),
                    CREATED_AT timestamp with time zone not null,
                    constraint {self.t('FK_EVAL_PROGRESS_RUN')}
                        foreign key (RUN_ID) references {self.t('EVALUATION_RUN')}(RUN_ID)
                )
            """)
            self._exec_ddl_ignore_exists(cur, f"create index {self.t('IX_EVAL_PROGRESS_RUN')} on {self.t('EVALUATION_PROGRESS_EVENT')}(RUN_ID, CREATED_AT)")

            self._exec_ddl_ignore_exists(cur, f"""
                create table {self.t('EVALUATION_ITEM')} (
                    ITEM_ID varchar2(64) primary key,
                    RUN_ID varchar2(64) not null,
                    TRACE_ID varchar2(256),
                    SESSION_ID varchar2(256),
                    MESSAGE_ID varchar2(256),
                    AGENT_ID varchar2(128),
                    CHANNEL varchar2(64),
                    STATUS varchar2(32) not null,
                    ATTEMPT_COUNT number default 0 not null,
                    ERROR_MESSAGE clob,
                    RAW_JSON clob check (RAW_JSON is json),
                    CREATED_AT timestamp with time zone not null,
                    UPDATED_AT timestamp with time zone not null,
                    constraint {self.t('FK_EVAL_ITEM_RUN')}
                        foreign key (RUN_ID) references {self.t('EVALUATION_RUN')}(RUN_ID)
                )
            """)
            self._exec_ddl_ignore_exists(cur, f"create index {self.t('IX_EVAL_ITEM_RUN')} on {self.t('EVALUATION_ITEM')}(RUN_ID, STATUS, CREATED_AT)")

            self._exec_ddl_ignore_exists(cur, f"""
                create table {self.t('EVALUATION_RESULT')} (
                    RESULT_ID varchar2(64) primary key,
                    RUN_ID varchar2(64) not null,
                    ITEM_ID varchar2(64),
                    TRACE_ID varchar2(256),
                    SESSION_ID varchar2(256),
                    AGENT_ID varchar2(128),
                    JUDGE_NAME varchar2(128) not null,
                    JUDGE_TYPE varchar2(32),
                    SCORE number,
                    JUDGE_SCORE number,
                    ACCURACY_SCORE number,
                    ALUCINATION_SCORE number,
                    HALLUCINATION_SCORE number,
                    INFERRED_CSI_SCORE number,
                    RESOLUTION number,
                    CONVERSATION_PRECISION number,
                    TOOL_USAGE_SCORE number,
                    ROUTING_SCORE number,
                    RATIONALE clob,
                    REASONING clob,
                    RESULT_JSON clob check (RESULT_JSON is json),
                    CREATED_AT timestamp with time zone not null,
                    constraint {self.t('FK_EVAL_RESULT_RUN')}
                        foreign key (RUN_ID) references {self.t('EVALUATION_RUN')}(RUN_ID),
                    constraint {self.t('FK_EVAL_RESULT_ITEM')}
                        foreign key (ITEM_ID) references {self.t('EVALUATION_ITEM')}(ITEM_ID)
                )
            """)
            self._exec_ddl_ignore_exists(cur, f"create index {self.t('IX_EVAL_RESULT_RUN')} on {self.t('EVALUATION_RESULT')}(RUN_ID, ITEM_ID)")

            self._exec_ddl_ignore_exists(cur, f"""
                create table {self.t('EVALUATION_METRIC')} (
                    METRIC_ID varchar2(64) primary key,
                    RUN_ID varchar2(64) not null,
                    ITEM_ID varchar2(64),
                    METRIC_NAME varchar2(128) not null,
                    METRIC_VALUE number,
                    DIMENSIONS_JSON clob check (DIMENSIONS_JSON is json),
                    CREATED_AT timestamp with time zone not null,
                    constraint {self.t('FK_EVAL_METRIC_RUN')}
                        foreign key (RUN_ID) references {self.t('EVALUATION_RUN')}(RUN_ID)
                )
            """)

            self._exec_ddl_ignore_exists(cur, f"""
                create table {self.t('EVALUATION_FINDING')} (
                    FINDING_ID varchar2(64) primary key,
                    RUN_ID varchar2(64) not null,
                    ITEM_ID varchar2(64),
                    SEVERITY varchar2(32),
                    CATEGORY varchar2(128),
                    TITLE varchar2(512),
                    DESCRIPTION clob,
                    EVIDENCE_JSON clob check (EVIDENCE_JSON is json),
                    CREATED_AT timestamp with time zone not null,
                    constraint {self.t('FK_EVAL_FINDING_RUN')}
                        foreign key (RUN_ID) references {self.t('EVALUATION_RUN')}(RUN_ID)
                )
            """)

            # Non-destructive compatibility for older generated schemas.
            for col, typ in [
                ("RETRY_COUNT", "number default 0"),
                ("ERROR_MESSAGE", "clob"),
                ("LAST_HEARTBEAT_AT", "timestamp with time zone"),
                ("UPDATED_AT", "timestamp with time zone"),
            ]:
                self._ensure_column(cur, "EVALUATION_RUN", col, typ)
            for col, typ in [
                ("ID", "number generated always as identity"),
            ]:
                # Identity column cannot always be added cleanly; ignore if table is old without ID.
                try:
                    self._ensure_column(cur, "EVALUATION_PROGRESS_EVENT", col, typ)
                except Exception:
                    pass
            for col, typ in [
                ("JUDGE_NAME", "varchar2(128) default 'unknown_judge' not null"),
                ("JUDGE_TYPE", "varchar2(32)"),
                ("SCORE", "number"),
                ("JUDGE_SCORE", "number"),
                ("ACCURACY_SCORE", "number"),
                ("ALUCINATION_SCORE", "number"),
                ("HALLUCINATION_SCORE", "number"),
                ("INFERRED_CSI_SCORE", "number"),
                ("RESOLUTION", "number"),
                ("CONVERSATION_PRECISION", "number"),
                ("TOOL_USAGE_SCORE", "number"),
                ("ROUTING_SCORE", "number"),
                ("RATIONALE", "clob"),
                ("REASONING", "clob"),
                ("RESULT_JSON", "clob"),
            ]:
                self._ensure_column(cur, "EVALUATION_RESULT", col, typ)
