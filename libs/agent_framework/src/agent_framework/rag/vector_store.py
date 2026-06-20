from __future__ import annotations

import asyncio
import json
import math
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from agent_framework.persistence.sqlite_store import SQLiteStore, _json_dumps, _json_loads


@dataclass
class VectorDocument:
    id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


class VectorStore:
    async def add_texts(self, texts: list[str], metadatas: list[dict] | None = None, namespace: str = "default") -> list[str]: ...
    async def similarity_search(self, query: str, k: int = 5, namespace: str = "default") -> list[VectorDocument]: ...


def _tokens(s: str): return re.findall(r"\w+", (s or "").lower(), flags=re.UNICODE)
def _score(q: str, d: str):
    qt = _tokens(q); dt = _tokens(d)
    if not qt or not dt: return 0.0
    ds = set(dt)
    return sum(1 for t in qt if t in ds) / math.sqrt(len(dt))

def _lob_value(value):
    return value.read() if hasattr(value, "read") else value


class InMemoryVectorStore(VectorStore):
    def __init__(self): self.docs: dict[str, list[VectorDocument]] = {}
    async def add_texts(self, texts, metadatas=None, namespace="default"):
        ids=[]; metadatas=metadatas or [{} for _ in texts]
        for text, meta in zip(texts, metadatas):
            did=str(uuid.uuid4()); ids.append(did)
            self.docs.setdefault(namespace, []).append(VectorDocument(id=did, content=text, metadata=meta))
        return ids
    async def similarity_search(self, query, k=5, namespace="default"):
        scored=[VectorDocument(id=d.id, content=d.content, metadata=d.metadata, score=_score(query,d.content)) for d in self.docs.get(namespace, [])]
        return sorted(scored, key=lambda x: x.score, reverse=True)[:k]


class SQLiteVectorStore(VectorStore):
    def __init__(self, settings, embedding_provider=None, telemetry=None):
        self.store=SQLiteStore(settings.SQLITE_DB_PATH)
        self.embedding_provider=embedding_provider
        self.telemetry=telemetry

    async def _embed(self, text: str):
        if not self.embedding_provider:
            return None
        start=time.time()
        if hasattr(self.embedding_provider, "aembed_query"):
            emb = await self.embedding_provider.aembed_query(text)
        elif hasattr(self.embedding_provider, "embed_query"):
            maybe = self.embedding_provider.embed_query(text)
            emb = await maybe if asyncio.iscoroutine(maybe) else maybe
        else:
            emb = None
        if self.telemetry:
            await self.telemetry.rag_event("embedding.completed", text[:256], 1 if emb else 0, {"latency_ms": int((time.time()-start)*1000), "dimensions": len(emb or [])})
        return emb

    async def add_texts(self, texts, metadatas=None, namespace="default"):
        metadatas=metadatas or [{} for _ in texts]; ids=[]
        with self.store._lock, self.store.connect() as con:
            for text, meta in zip(texts, metadatas):
                did=str(uuid.uuid4()); ids.append(did)
                emb=await self._embed(text)
                con.execute(
                    "insert into rag_documents(id, namespace, content, embedding_json, metadata_json, created_at) values(?,?,?,?,?,?)",
                    (did, namespace, text, json.dumps(emb) if emb is not None else None, _json_dumps(meta), self.store.now())
                )
        return ids

    async def similarity_search(self, query, k=5, namespace="default"):
        query_emb=await self._embed(query)
        with self.store._lock, self.store.connect() as con:
            rows=con.execute("select * from rag_documents where namespace=?", (namespace,)).fetchall()
        docs=[]
        for r in rows:
            content=r["content"]
            emb=_json_loads(r["embedding_json"] if "embedding_json" in r.keys() else None, None)
            if query_emb is not None and emb:
                score=_cosine(query_emb, emb)
            else:
                score=_score(query, content)
            docs.append(VectorDocument(id=r["id"], content=content, metadata=_json_loads(r["metadata_json"], {}), score=score))
        return sorted(docs, key=lambda x: x.score, reverse=True)[:k]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n=min(len(a), len(b))
    dot=sum(float(a[i])*float(b[i]) for i in range(n))
    na=math.sqrt(sum(float(x)*float(x) for x in a[:n]))
    nb=math.sqrt(sum(float(x)*float(x) for x in b[:n]))
    if not na or not nb:
        return 0.0
    return dot/(na*nb)


class OracleVectorStore(VectorStore):
    """Oracle 23ai Vector Store using VECTOR_DISTANCE and optional vector index."""
    def __init__(self, settings, embedding_provider=None, telemetry=None):
        from agent_framework.persistence.oracle_store import OracleStore
        self.store=OracleStore(settings)
        self.settings=settings
        self.embedding_provider=embedding_provider
        self.telemetry=telemetry
        self._try_init_vector_index()

    def _try_init_vector_index(self):
        try:
            self.store.try_create_vector_index()
        except Exception:
            # Index may not be available in all local/test DBs; table still works.
            pass

    async def _embed(self, text: str):
        if not self.embedding_provider: return None
        start=time.time()
        if hasattr(self.embedding_provider, "aembed_query"):
            emb = await self.embedding_provider.aembed_query(text)
        elif hasattr(self.embedding_provider, "embed_query"):
            maybe = self.embedding_provider.embed_query(text)
            emb = await maybe if asyncio.iscoroutine(maybe) else maybe
        else:
            emb = None
        if self.telemetry:
            await self.telemetry.rag_event("embedding.completed", text[:256], 1 if emb else 0, {"latency_ms": int((time.time()-start)*1000), "dimensions": len(emb or [])})
        return emb

    async def add_texts(self, texts, metadatas=None, namespace="default"):
        ids=[]; metadatas=metadatas or [{} for _ in texts]
        start=time.time()
        for text, meta in zip(texts, metadatas):
            did=str(uuid.uuid4()); ids.append(did)
            emb=await self._embed(text)
            await self.store.rag_add_text(did, namespace, text, meta, emb)
        if self.telemetry:
            await self.telemetry.rag_event("add_texts", namespace, len(ids), {"namespace": namespace, "latency_ms": int((time.time()-start)*1000)})
        return ids

    async def similarity_search(self, query, k=5, namespace="default"):
        start=time.time()
        emb=await self._embed(query)
        if emb is None:
            docs=await asyncio.to_thread(self._lexical_search_sync, query, k, namespace)
            mode="lexical_fallback"
        else:
            docs=await asyncio.to_thread(self._vector_search_sync, emb, k, namespace)
            mode="oracle_vector"
        if self.telemetry:
            await self.telemetry.rag_event("similarity_search", query, len(docs), {"namespace": namespace, "k": k, "mode": mode, "latency_ms": int((time.time()-start)*1000), "top_scores": [round(d.score, 6) for d in docs[:5]]})
        return docs

    def _lexical_search_sync(self, query, k, namespace):
        with self.store.connect() as conn:
            cur=conn.cursor()
            cur.execute(f"select ID, CONTENT, METADATA_JSON from {self.store.t('RAG_DOCUMENT')} where NAMESPACE=:1", [namespace])
            out=[]
            for i, c, m in cur.fetchall():
                content=_lob_value(c) or ""
                out.append(VectorDocument(id=i, content=content, metadata=_json_loads(_lob_value(m), {}), score=_score(query, content)))
            return sorted(out, key=lambda x: x.score, reverse=True)[:k]

    def _vector_search_sync(self, embedding, k, namespace):
        emb_json=json.dumps(embedding)
        with self.store.connect() as conn:
            cur=conn.cursor()
            cur.execute(f"""
                select ID, CONTENT, METADATA_JSON, VECTOR_DISTANCE(EMBEDDING, TO_VECTOR(:embedding), COSINE) as DIST
                  from {self.store.t('RAG_DOCUMENT')}
                 where NAMESPACE=:namespace and EMBEDDING is not null
                 order by DIST asc
                 fetch first :limit rows only
            """, {"embedding": emb_json, "namespace": namespace, "limit": int(k)})
            out=[]
            for i, c, m, dist in cur.fetchall():
                out.append(VectorDocument(id=i, content=_lob_value(c) or "", metadata=_json_loads(_lob_value(m), {}), score=1.0 - float(dist or 0)))
            return out


AutonomousVectorStore=OracleVectorStore


def create_vector_store(settings, embedding_provider=None, telemetry=None):
    provider=getattr(settings, "VECTOR_STORE_PROVIDER", "memory")
    if provider == "sqlite": return SQLiteVectorStore(settings, embedding_provider=embedding_provider, telemetry=telemetry)
    if provider in {"autonomous", "oracle"}: return OracleVectorStore(settings, embedding_provider=embedding_provider, telemetry=telemetry)
    return InMemoryVectorStore()
