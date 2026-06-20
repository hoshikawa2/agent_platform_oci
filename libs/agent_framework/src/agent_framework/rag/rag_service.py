from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .vector_store import VectorDocument, create_vector_store
from .graph_store import create_graph_store


@dataclass
class RagResult:
    query: str
    documents: list[VectorDocument]
    graph_neighbors: list[Any]
    latency_ms: int
    metadata: dict[str, Any]

    def as_prompt_context(self, max_chars: int = 6000) -> str:
        chunks=[]; total=0
        for i, doc in enumerate(self.documents, start=1):
            text=(doc.content or '').strip()
            if not text: continue
            piece=f"[doc:{i} score={doc.score:.4f} id={doc.id}]\n{text}\n"
            if total + len(piece) > max_chars: break
            chunks.append(piece); total += len(piece)
        return "\n".join(chunks)


class RagService:
    """RAG operacional: vector search + grafo + telemetria FIRST-like.

    LLM hooks are optional. Existing behavior remains retrieval-only unless an
    LLM is injected and the caller explicitly calls rewrite/generate/compress.
    Each hook uses a dedicated profile:
      - rag_rewriter
      - rag_generation
      - rag_compressor
    """

    def __init__(self, settings, embedding_provider=None, telemetry=None, llm: Any | None = None):
        self.settings=settings
        self.telemetry=telemetry
        self.llm=llm
        self.vector_store=create_vector_store(settings, embedding_provider=embedding_provider, telemetry=telemetry)
        self.graph_store=create_graph_store(settings, telemetry=telemetry)

    async def add_documents(self, texts: list[str], metadatas: list[dict] | None = None, namespace: str='default') -> list[str]:
        start=time.time()
        ids=await self.vector_store.add_texts(texts, metadatas=metadatas, namespace=namespace)
        if self.telemetry:
            await self.telemetry.rag_event('documents.added', namespace, len(ids), {
                'namespace': namespace, 'document_count': len(ids), 'latency_ms': int((time.time()-start)*1000)
            })
        return ids

    async def retrieve(self, query: str, *, namespace: str='default', k: int | None=None, graph_node: str | None=None, rewrite: bool = False) -> RagResult:
        start=time.time(); k=k or self.settings.RAG_TOP_K
        effective_query = await self.rewrite_query(query, namespace=namespace) if rewrite else query
        docs=await self.vector_store.similarity_search(effective_query, k=k, namespace=namespace)
        neighbors=[]
        if graph_node:
            neighbors=await self.graph_store.neighbors(graph_node)
        result=RagResult(query=effective_query, documents=docs, graph_neighbors=neighbors, latency_ms=int((time.time()-start)*1000), metadata={'namespace':namespace,'k':k, 'original_query': query, 'rewritten': rewrite and effective_query != query})
        if self.telemetry:
            await self.telemetry.rag_event('retrieve.completed', effective_query, len(docs), {
                'namespace': namespace, 'k': k, 'latency_ms': result.latency_ms, 'graph_neighbors': len(neighbors),
                'top_scores': [round(d.score, 6) for d in docs[:5]], 'rewritten': result.metadata.get('rewritten'),
            })
        return result

    async def rewrite_query(self, query: str, *, namespace: str = 'default', profile_name: str = 'rag_rewriter') -> str:
        if not self.llm:
            return query
        prompt = (
            'Reescreva a pergunta para busca semântica/RAG. Preserve termos de negócio, IDs, nomes de produtos e datas.\n'
            'Responda apenas com a consulta reescrita, sem explicações.\n\n'
            f'Namespace: {namespace}\nPergunta: {query}'
        )
        try:
            rewritten = await self.llm.ainvoke(
                [
                    {'role': 'system', 'content': 'Você otimiza consultas para retrieval. Responda só a consulta.'},
                    {'role': 'user', 'content': prompt},
                ],
                temperature=0,
                max_tokens=300,
                profile_name=profile_name,
                component_name=profile_name,
                generation_name=f"llm.{profile_name}",
            )
            value = str(rewritten or '').strip()
            return value or query
        except Exception:
            if self.telemetry:
                await self.telemetry.rag_event('rewrite.failed', query, 0, {'namespace': namespace, 'profile_name': profile_name})
            return query

    async def compress_context(self, rag_result: RagResult, *, question: str, max_chars: int = 4000, profile_name: str = 'rag_compressor') -> str:
        context = rag_result.as_prompt_context(max_chars=max_chars * 3)
        if not self.llm or len(context) <= max_chars:
            return context[:max_chars]
        prompt = (
            'Comprima o contexto RAG mantendo somente evidências úteis para responder a pergunta.\n'
            'Não invente fatos. Mantenha IDs de documentos quando presentes.\n\n'
            f'Pergunta: {question}\n\nContexto:\n{context[:20000]}'
        )
        try:
            compressed = await self.llm.ainvoke(
                [
                    {'role': 'system', 'content': 'Você comprime contexto RAG sem alterar fatos.'},
                    {'role': 'user', 'content': prompt},
                ],
                temperature=0,
                max_tokens=max(512, max_chars // 3),
                profile_name=profile_name,
                component_name=profile_name,
                generation_name=f"llm.{profile_name}",
            )
            return str(compressed or '').strip()[:max_chars]
        except Exception:
            if self.telemetry:
                await self.telemetry.rag_event('compress.failed', question, len(rag_result.documents), {'profile_name': profile_name})
            return context[:max_chars]

    async def generate_answer(self, question: str, rag_result: RagResult, *, profile_name: str = 'rag_generation', max_context_chars: int = 6000) -> str:
        if not self.llm:
            raise RuntimeError('RagService.generate_answer requires llm')
        context = await self.compress_context(rag_result, question=question, max_chars=max_context_chars)
        prompt = (
            'Responda a pergunta usando prioritariamente o contexto RAG.\n'
            'Se o contexto não tiver evidência suficiente, diga isso claramente.\n\n'
            f'Pergunta:\n{question}\n\nContexto RAG:\n{context}'
        )
        answer = await self.llm.ainvoke(
            [
                {'role': 'system', 'content': 'Você é um assistente RAG corporativo. Não invente evidências.'},
                {'role': 'user', 'content': prompt},
            ],
            profile_name=profile_name,
            component_name=profile_name,
            generation_name=f"llm.{profile_name}",
        )
        if self.telemetry:
            await self.telemetry.rag_event('generation.completed', question, len(rag_result.documents), {'profile_name': profile_name})
        return str(answer or '')
