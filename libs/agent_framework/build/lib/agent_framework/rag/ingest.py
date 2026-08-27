from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass
class LoadedDocument:
    source: str
    text: str
    metadata: dict[str, Any]


@dataclass
class DocumentChunk:
    id: str
    text: str
    metadata: dict[str, Any]


@dataclass
class IngestResult:
    namespace: str
    files_read: int
    chunks_created: int
    documents_saved: int

def parse_csv(value: str | None, default: list[str] | None = None) -> list[str]:
    if value is None or not str(value).strip():
        return default or []

    return [
        item.strip()
        for item in str(value).split(",")
        if item.strip()
    ]


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _read_pdf_file(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "PDF support requires pypdf. Install it with: pip install pypdf"
        ) from exc

    reader = PdfReader(str(path))
    pages: list[str] = []

    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"\n\n[Page {page_number}]\n{text}")

    return "\n".join(pages).strip()


def load_documents(
        docs_dir: str | Path,
        globs: list[str] | None = None,
) -> list[LoadedDocument]:
    docs_path = Path(docs_dir)

    if not docs_path.exists():
        raise FileNotFoundError(f"Documents directory not found: {docs_path}")

    if globs is None:
        globs = ["*.md", "*.txt", "*.yaml", "*.yml", "*.json", "*.pdf"]

    documents: list[LoadedDocument] = []
    seen: set[Path] = set()

    for pattern in globs:
        for path in sorted(docs_path.rglob(pattern)):
            if not path.is_file():
                continue

            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)

            suffix = path.suffix.lower()

            if suffix == ".pdf":
                text = _read_pdf_file(path)
            else:
                text = _read_text_file(path)

            if not text.strip():
                continue

            documents.append(
                LoadedDocument(
                    source=str(path),
                    text=text,
                    metadata={
                        "source": path.name,
                        "path": str(path),
                        "extension": suffix,
                    },
                )
            )

    return documents


def chunk_text(
        text: str,
        chunk_size: int | None = 1200,
        chunk_overlap: int | None = 200,
) -> list[str]:
    chunk_size = int(chunk_size or 1200)
    chunk_overlap = int(chunk_overlap or 200)

    text = text.strip()

    if not text:
        return []

    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = max(0, end - chunk_overlap)

    return chunks


def _stable_chunk_id(namespace: str, source: str, index: int, text: str) -> str:
    digest = hashlib.sha256(
        f"{namespace}:{source}:{index}:{text[:200]}".encode("utf-8")
    ).hexdigest()[:24]

    return f"{namespace}:{Path(source).name}:{index}:{digest}"


def build_chunks(
        documents: list[LoadedDocument],
        namespace: str,
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []

    for doc in documents:
        text_chunks = chunk_text(
            doc.text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        total = len(text_chunks)

        for index, text in enumerate(text_chunks):
            source_name = doc.metadata.get("source", "document")

            metadata = {
                **doc.metadata,
                "namespace": namespace,
                "chunk_index": index,
                "chunk_total": total,
            }

            chunks.append(
                DocumentChunk(
                    id=_stable_chunk_id(namespace, source_name, index, text),
                    text=text,
                    metadata=metadata,
                )
            )

    return chunks


async def _save_chunk(
        vector_store: Any,
        *,
        namespace: str,
        chunk: DocumentChunk,
        embedding: list[float] | None,
) -> None:
    """
    Saves one RAG chunk into the configured vector store.

    Compatibility rules:

    1. If the vector store exposes add_document/upsert_document, use the richer API.
    2. If it only exposes add_texts, use the LangChain-like API.
    3. Do not pass ids=... to OracleVectorStore.add_texts(), because this
       implementation generates its own UUID internally.
    """

    metadata = {
        **chunk.metadata,
        "chunk_id": chunk.id,
    }

    if hasattr(vector_store, "add_document"):
        try:
            result = vector_store.add_document(
                id=chunk.id,
                namespace=namespace,
                content=chunk.text,
                metadata=metadata,
                embedding=embedding,
            )

            if asyncio.iscoroutine(result):
                await result

            return

        except TypeError:
            pass

    if hasattr(vector_store, "upsert_document"):
        try:
            result = vector_store.upsert_document(
                id=chunk.id,
                namespace=namespace,
                content=chunk.text,
                metadata=metadata,
                embedding=embedding,
            )

            if asyncio.iscoroutine(result):
                await result

            return

        except TypeError:
            pass

    if hasattr(vector_store, "add_texts"):
        try:
            result = vector_store.add_texts(
                texts=[chunk.text],
                metadatas=[metadata],
                namespace=namespace,
            )

            if asyncio.iscoroutine(result):
                await result

            return

        except TypeError:
            result = vector_store.add_texts(
                texts=[chunk.text],
                metadatas=[metadata],
            )

            if asyncio.iscoroutine(result):
                await result

            return

    raise AttributeError(
        "Vector store does not expose add_document, upsert_document or add_texts"
    )


async def ingest_documents(
        settings: Any | None = None,
        *,
        docs_dir: str | Path,
        namespace: str,
        vector_store: Any | None = None,
        embedding_provider: Any | None = None,
        globs: list[str] | None = None,
        file_globs: list[str] | None = None,
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
) -> IngestResult:
    """
    Ingest documents into the configured vector store.

    This function intentionally accepts both `globs` and `file_globs`
    because the CLI script uses `file_globs`, while older internal code
    may use `globs`.
    """
    chunk_size = int(chunk_size or 1200)
    chunk_overlap = int(chunk_overlap or 200)

    effective_globs = file_globs or globs

    if embedding_provider is None:
        from agent_framework.rag.embedding_provider import create_embedding_provider
        embedding_provider = create_embedding_provider(settings)

    if vector_store is None:
        from agent_framework.rag.vector_store import create_vector_store
        vector_store = create_vector_store(
            settings,
            embedding_provider=embedding_provider,
            telemetry=None,
        )

    if getattr(vector_store, "embedding_provider", None) is None:
        vector_store.embedding_provider = embedding_provider

    documents = load_documents(
        docs_dir=docs_dir,
        globs=effective_globs,
    )

    chunks = build_chunks(
        documents=documents,
        namespace=namespace,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    documents_saved = 0

    for chunk in chunks:
        embedding: list[float] | None = None

        if embedding_provider is not None:
            if hasattr(embedding_provider, "embed_query"):
                result = embedding_provider.embed_query(chunk.text)
            elif hasattr(embedding_provider, "embed_text"):
                result = embedding_provider.embed_text(chunk.text)
            elif hasattr(embedding_provider, "embed"):
                result = embedding_provider.embed(chunk.text)
            else:
                raise AttributeError(
                    "Embedding provider does not expose embed_query, embed_text or embed"
                )

            if asyncio.iscoroutine(result):
                result = await result

            embedding = result

        await _save_chunk(
            vector_store,
            namespace=namespace,
            chunk=chunk,
            embedding=embedding,
        )

        documents_saved += 1

    return IngestResult(
        namespace=namespace,
        files_read=len(documents),
        chunks_created=len(chunks),
        documents_saved=documents_saved,
    )


def ingest_documents_sync(
        settings=None,
        *,
        docs_dir,
        namespace,
        vector_store=None,
        embedding_provider=None,
        file_globs=None,
        globs=None,
        chunk_size=1200,
        chunk_overlap=200,
) -> IngestResult:
    chunk_size = int(chunk_size or 1200)
    chunk_overlap = int(chunk_overlap or 200)

    effective_globs = file_globs or globs

    return asyncio.run(
        ingest_documents(
            settings,
            docs_dir=docs_dir,
            namespace=namespace,
            vector_store=vector_store,
            embedding_provider=embedding_provider,
            file_globs=effective_globs,
            globs=effective_globs,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    )