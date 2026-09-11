from __future__ import annotations

import asyncio
import json
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from .vector_store import VectorDocument


def _lob_value(value: Any) -> Any:
    return value.read() if hasattr(value, "read") else value


@dataclass(frozen=True)
class KbdbOracleSettings:
    """Credenciais Oracle exclusivas do Autonomous usado pelo KBDB.

    A semântica é deliberadamente a mesma já usada pelo OracleStore do
    framework: ``dsn`` é o alias TNS da wallet, ``config_dir`` e
    ``wallet_location`` apontam para a pasta da wallet e ``wallet_password``
    é repassado ao python-oracledb. O KBDB não reutiliza/faz fallback para
    ``ADB_*`` porque pode residir em outro Autonomous.
    """

    user: str
    password: str
    dsn: str
    wallet_location: str | None = None
    wallet_password: str | None = None


class KbdbRagService:
    """Enterprise KBDB serving adapter.

    This adapter deliberately integrates only the stable serving facade
    PKG_KB_SERVING.SEARCH_KNOWLEDGE_BASE. KBDB ingestion/publication/lifecycle stay
    outside the agent runtime.
    """

    def __init__(self, settings, telemetry=None):
        self.settings = settings
        self.telemetry = telemetry
        self.db = KbdbOracleSettings(
            user=str(getattr(settings, "KBDB_DB_USER", None) or ""),
            password=str(getattr(settings, "KBDB_DB_PASSWORD", None) or ""),
            dsn=str(getattr(settings, "KBDB_DB_DSN", None) or ""),
            wallet_location=getattr(settings, "KBDB_DB_WALLET_LOCATION", None),
            wallet_password=getattr(settings, "KBDB_DB_WALLET_PASSWORD", None),
        )
        if not self.db.user or not self.db.password or not self.db.dsn:
            raise RuntimeError(
                "KBDB_DB_USER, KBDB_DB_PASSWORD e KBDB_DB_DSN são obrigatórios "
                "quando RAG_PROVIDER=kbdb"
            )

    @contextmanager
    def _connect(self):
        """Abre conexão seguindo o mesmo padrão já usado pelo OracleStore.

        Esta implementação é intencionalmente local ao KBDB para não alterar
        OracleStore, Long-Term Memory ou qualquer outro consumidor Oracle já
        existente no framework.
        """
        import oracledb

        oracledb.defaults.fetch_lobs = False
        kwargs: dict[str, Any] = {}
        if self.db.wallet_location:
            kwargs["config_dir"] = self.db.wallet_location
            kwargs["wallet_location"] = self.db.wallet_location
        if self.db.wallet_password:
            kwargs["wallet_password"] = self.db.wallet_password

        conn = oracledb.connect(
            user=self.db.user,
            password=self.db.password,
            dsn=self.db.dsn,
            **kwargs,
        )
        try:
            yield conn
        finally:
            conn.close()

    @staticmethod
    def _procedure_arguments(cur) -> list[dict[str, Any]]:
        """Discover the installed facade signature instead of assuming bind types."""
        cur.execute(
            """
            SELECT argument_name, position, in_out, data_type, overload
              FROM all_arguments
             WHERE package_name = 'PKG_KB_SERVING'
               AND object_name = 'SEARCH_KNOWLEDGE_BASE'
               AND data_level = 0
             ORDER BY NVL(overload, '0'), sequence
            """
        )
        rows = cur.fetchall()
        if not rows:
            return []
        # Use the first visible overload. Each returned row describes one bind.
        first_overload = rows[0][4]
        return [
            {
                "name": str(row[0] or ""),
                "position": int(row[1] or 0),
                "in_out": str(row[2] or "IN").upper(),
                "data_type": str(row[3] or "").upper(),
            }
            for row in rows
            if row[4] == first_overload and int(row[1] or 0) > 0
        ]

    @staticmethod
    def _out_var(cur, oracledb, data_type: str):
        if data_type == "JSON" and hasattr(oracledb, "DB_TYPE_JSON"):
            return cur.var(oracledb.DB_TYPE_JSON)
        if data_type in {"CLOB", "NCLOB"} and hasattr(oracledb, "DB_TYPE_CLOB"):
            return cur.var(oracledb.DB_TYPE_CLOB)
        return cur.var(oracledb.DB_TYPE_VARCHAR, size=32767)

    def _search_sync(self, query: str, k: int) -> dict[str, Any]:
        import oracledb
        metadata = self.settings.KBDB_METADATA_JSON
        if metadata:
            # validate early; procedure expects JSON text
            json.loads(metadata)
        with self._connect() as conn:
            cur = conn.cursor()
            if self.settings.KBDB_MIN_SCORE is not None:
                cur.callproc("PKG_KB_SERVING.set_min_score", [float(self.settings.KBDB_MIN_SCORE)])
            signature = self._procedure_arguments(cur)
            if not signature:
                raise RuntimeError(
                    "Não foi possível descobrir a assinatura de "
                    "PKG_KB_SERVING.SEARCH_KNOWLEDGE_BASE em ALL_ARGUMENTS"
                )
            canonical_inputs = [
                self.settings.KBDB_SEARCH_TYPE,
                query,
                int(k),
                bool(self.settings.KBDB_NODE_EXPANSION),
                int(self.settings.KBDB_NODE_MAX_RELATED),
                bool(self.settings.KBDB_GRAPH_CROSS_REF),
                int(self.settings.KBDB_MAX_CROSS_REF_HOPS),
                self.settings.KBDB_DOCUMENT_TYPE or None,
                metadata or None,
                bool(getattr(self.settings, "KBDB_IDENTIFY_DOCUMENT", True)),
                bool(getattr(self.settings, "KBDB_STORE_QUERY", True)),
                int(getattr(self.settings, "KBDB_IDENTIFY_TOP_N", 3)),
            ]
            named_inputs = {
                "SEARCH_TYPE": self.settings.KBDB_SEARCH_TYPE,
                "QUERY": query,
                "QUERY_TEXT": query,
                "QUESTION": query,
                "TOP_K": int(k),
                "K": int(k),
                "NODE_EXPANSION": bool(self.settings.KBDB_NODE_EXPANSION),
                "ENABLE_NODE_EXPANSION": bool(self.settings.KBDB_NODE_EXPANSION),
                "NODE_MAX_RELATED": int(self.settings.KBDB_NODE_MAX_RELATED),
                "MAX_RELATED_NODES": int(self.settings.KBDB_NODE_MAX_RELATED),
                "GRAPH_CROSS_REF": bool(self.settings.KBDB_GRAPH_CROSS_REF),
                "ENABLE_GRAPH_CROSS_REF": bool(self.settings.KBDB_GRAPH_CROSS_REF),
                "MAX_CROSS_REF_HOPS": int(self.settings.KBDB_MAX_CROSS_REF_HOPS),
                "DOCUMENT_TYPE": self.settings.KBDB_DOCUMENT_TYPE or None,
                "METADATA_JSON": metadata or None,
                "METADATA": metadata or None,
                "IDENTIFY_DOCUMENT": bool(getattr(self.settings, "KBDB_IDENTIFY_DOCUMENT", True)),
                "STORE_QUERY": bool(getattr(self.settings, "KBDB_STORE_QUERY", True)),
                "IDENTIFY_TOP_N": int(getattr(self.settings, "KBDB_IDENTIFY_TOP_N", 3)),
            }
            input_index = 0
            binds: list[Any] = []
            out = None
            for argument in signature:
                if "OUT" in argument["in_out"]:
                    bind = self._out_var(cur, oracledb, argument["data_type"])
                    binds.append(bind)
                    out = bind
                    continue
                if input_index >= len(canonical_inputs):
                    raise RuntimeError(
                        "Assinatura KBDB possui parâmetros de entrada não suportados: "
                        f"{[item['name'] for item in signature]}"
                    )
                normalized_name = argument["name"].strip().upper()
                if normalized_name.startswith("P_"):
                    normalized_name = normalized_name[2:]
                value = named_inputs.get(normalized_name, canonical_inputs[input_index])
                input_index += 1
                if argument["data_type"] == "NUMBER" and isinstance(value, bool):
                    value = 1 if value else 0
                elif argument["data_type"] in {"VARCHAR", "VARCHAR2", "CHAR", "NCHAR"} and isinstance(value, bool):
                    value = "true" if value else "false"
                binds.append(value)
            if out is None:
                raise RuntimeError("Assinatura KBDB não possui parâmetro OUT visível")
            cur.callproc("PKG_KB_SERVING.search_knowledge_base", binds)
            value = _lob_value(out.getvalue())
            if isinstance(value, str):
                return json.loads(value)
            return dict(value or {})

    async def retrieve(self, query: str, *, namespace: str = "default", k: int | None = None,
                       graph_node: str | None = None, rewrite: bool = False):
        # rewrite is intentionally handled by the framework's RagService wrapper.
        from .rag_service import RagResult
        start = time.time()
        k = k or self.settings.RAG_TOP_K
        envelope = await asyncio.to_thread(self._search_sync, query, k)
        seeds = {str(s.get("unit_id")): s for s in (envelope.get("seeds") or []) if isinstance(s, dict)}
        docs: list[VectorDocument] = []
        for unit in envelope.get("units") or []:
            if not isinstance(unit, dict):
                continue
            unit_id = str(unit.get("unit_id") or unit.get("id") or "")
            content = str(unit.get("content") or "").strip()
            if not unit_id or not content:
                continue
            seed = seeds.get(unit_id, {})
            score = float(seed.get("score") or unit.get("score") or 0.0)
            docs.append(VectorDocument(id=unit_id, content=content, metadata={**unit, "kbdb_envelope": False}, score=score))
        latency_ms = int((time.time() - start) * 1000)
        metadata_out = {
            "provider": "kbdb",
            "namespace": namespace,
            "k": k,
            "search_type": envelope.get("search_type") or self.settings.KBDB_SEARCH_TYPE,
            "confidence": envelope.get("confidence"),
            "low_confidence": bool(envelope.get("low_confidence")),
            "warnings": envelope.get("warnings") or [],
            "documents": envelope.get("documents") or [],
            "top_score": envelope.get("top_score"),
            "fallback_reason": envelope.get("fallback_reason"),
            "envelope": envelope,
        }
        if self.telemetry:
            await self.telemetry.rag_event("retrieve.completed", query, len(docs), {
                "provider": "kbdb", "k": k, "latency_ms": latency_ms,
                "confidence": metadata_out["confidence"], "low_confidence": metadata_out["low_confidence"],
                "warning_count": len(metadata_out["warnings"]),
            })
        return RagResult(query=query, documents=docs, graph_neighbors=[], latency_ms=latency_ms, metadata=metadata_out)

    async def add_documents(self, *args, **kwargs):
        raise RuntimeError("RAG_PROVIDER=kbdb é serving-only; ingestão/publicação devem ser executadas pelo pipeline KBDB")
