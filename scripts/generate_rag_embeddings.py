#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK_SRC = ROOT / "agent_framework" / "src"
if str(FRAMEWORK_SRC) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_SRC))

from agent_framework.config.settings import get_settings
from agent_framework.rag.ingest import ingest_documents_sync, parse_csv


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate RAG embeddings and store document chunks in the configured vector store."
    )
    parser.add_argument("--docs-dir", default=None, help="Directory containing Markdown/text/YAML/JSON documents.")
    parser.add_argument("--namespace", default=None, help="RAG namespace used by the agent profile.")
    parser.add_argument("--globs", default=None, help="Comma-separated file globs. Example: '*.md,*.txt'.")
    parser.add_argument("--chunk-size", type=int, default=None, help="Maximum chunk size in characters.")
    parser.add_argument("--chunk-overlap", type=int, default=None, help="Chunk overlap in characters.")
    args = parser.parse_args()

    settings = get_settings()
    result = ingest_documents_sync(
        settings,
        docs_dir=args.docs_dir,
        namespace=args.namespace,
        file_globs=parse_csv(args.globs, []) or None,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )

    print("RAG embedding generation completed")
    print(f"  namespace:      {result.namespace}")
    print(f"  files read:     {result.files_read}")
    print(f"  chunks created: {result.chunks_created}")
    print(f"  documents saved:{result.documents_saved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
