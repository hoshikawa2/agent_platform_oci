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
            out = cur.var(oracledb.DB_TYPE_JSON)
            cur.callproc("PKG_KB_SERVING.search_knowledge_base", [
                self.settings.KBDB_SEARCH_TYPE,
                query,
                int(k),
                bool(self.settings.KBDB_NODE_EXPANSION),
                int(self.settings.KBDB_NODE_MAX_RELATED),
                bool(self.settings.KBDB_GRAPH_CROSS_REF),
                int(self.settings.KBDB_MAX_CROSS_REF_HOPS),
                self.settings.KBDB_DOCUMENT_TYPE or None,
                metadata or None,
                out,
            ])
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
