from __future__ import annotations

import time
from typing import Any


class InMemoryGraphStore:
    def __init__(self): self.edges=[]
    async def add_edge(self, src, rel, dst, metadata=None): self.edges.append((src, rel, dst, metadata or {}))
    async def neighbors(self, node): return [e for e in self.edges if e[0] == node or e[2] == node]
    async def pgql(self, query: str, binds: dict[str, Any] | None = None): return []


class OracleGraphStore:
    """Oracle Property Graph/PGQL provider.

    Uses GRAPH_NODE/GRAPH_EDGE tables and can create an Oracle property graph.
    `neighbors()` uses PGQL/GRAPH_TABLE when available and falls back to SQL edge
    lookup for portability.
    """
    def __init__(self, settings, telemetry=None):
        from agent_framework.persistence.oracle_store import OracleStore
        self.store=OracleStore(settings)
        self.telemetry=telemetry
        self.graph_name=getattr(settings, "ORACLE_GRAPH_NAME", "AGENTFW_GRAPH")
        if getattr(settings, "ORACLE_GRAPH_AUTO_CREATE", False):
            try: self.store.try_create_property_graph(self.graph_name)
            except Exception: pass

    async def add_edge(self, src, rel, dst, metadata=None):
        start=time.time()
        await self.store.graph_add_edge(src, rel, dst, metadata or {})
        if self.telemetry:
            await self.telemetry.event("rag.graph.edge.added", {"src": src, "rel": rel, "dst": dst, "latency_ms": int((time.time()-start)*1000)}, kind="rag")

    async def neighbors(self, node):
        start=time.time()
        try:
            rows=await self.store.graph_neighbors_pgql(self.graph_name, node)
            mode="pgql"
        except Exception:
            rows=await self.store.graph_neighbors(node)
            mode="sql_fallback"
        if self.telemetry:
            await self.telemetry.event("rag.graph.neighbors", {"node": node, "count": len(rows), "mode": mode, "latency_ms": int((time.time()-start)*1000)}, kind="rag")
        return rows

    async def pgql(self, query: str, binds: dict[str, Any] | None = None):
        rows=await self.store.graph_pgql(query, binds or {})
        if self.telemetry:
            await self.telemetry.event("rag.graph.pgql", {"rows": len(rows)}, kind="rag")
        return rows


AutonomousGraphStore=OracleGraphStore


def create_graph_store(settings, telemetry=None):
    provider=getattr(settings, "GRAPH_STORE_PROVIDER", "memory")
    if provider in {"autonomous", "oracle"}: return OracleGraphStore(settings, telemetry=telemetry)
    return InMemoryGraphStore()
