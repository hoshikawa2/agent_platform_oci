from __future__ import annotations

import asyncio
import hashlib
import math
from typing import Protocol


class EmbeddingProvider(Protocol):
    async def aembed_query(self, text: str) -> list[float]: ...


class MockEmbeddingProvider:
    """Deterministic local embedding provider for development and tests.

    This provider does not call external services. It creates a stable hashed
    vector so the RAG pipeline can be exercised locally. Use OCI in production.
    """

    def __init__(self, dimensions: int = 384):
        self.dimensions = int(dimensions)

    async def aembed_query(self, text: str) -> list[float]:
        return self._embed(text or "")

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text or "")

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = (text or "").lower().split()
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[idx] += sign

        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


class OCIEmbeddingProvider:
    """OCI Generative AI embedding provider.

    Uses the OCI Python SDK already declared by the framework. The client call is
    executed in a worker thread because the OCI SDK is synchronous.
    """

    def __init__(self, settings):
        import oci
        from oci.generative_ai_inference import GenerativeAiInferenceClient

        self.settings = settings
        self.model_id = settings.OCI_EMBEDDING_MODEL
        self.compartment_id = settings.OCI_COMPARTMENT_ID
        self.endpoint = self._resolve_endpoint(settings)

        if not self.compartment_id:
            raise ValueError("OCI_COMPARTMENT_ID is required when EMBEDDING_PROVIDER=oci")

        from agent_framework.oci.auth import get_oci_config_and_signer

        config, signer = get_oci_config_and_signer(settings)
        kwargs = {"config": config, "service_endpoint": self.endpoint}
        if signer is not None:
            kwargs["signer"] = signer
        self.client = GenerativeAiInferenceClient(**kwargs)

    @staticmethod
    def _resolve_endpoint(settings) -> str:
        endpoint = getattr(settings, "OCI_EMBEDDING_ENDPOINT", None)
        if endpoint:
            return endpoint
        region = getattr(settings, "OCI_REGION", "sa-saopaulo-1")
        return f"https://inference.generativeai.{region}.oci.oraclecloud.com"

    async def aembed_query(self, text: str) -> list[float]:
        return await asyncio.to_thread(self.embed_query, text)

    def embed_query(self, text: str) -> list[float]:
        from oci.generative_ai_inference.models import EmbedTextDetails, OnDemandServingMode

        details = EmbedTextDetails(
            compartment_id=self.compartment_id,
            serving_mode=OnDemandServingMode(model_id=self.model_id),
            inputs=[text or ""],
        )
        response = self.client.embed_text(details)
        embeddings = getattr(response.data, "embeddings", None) or []
        if not embeddings:
            return []
        return list(embeddings[0])


def create_embedding_provider(settings):
    provider = getattr(settings, "EMBEDDING_PROVIDER", "mock")
    if provider == "oci":
        return OCIEmbeddingProvider(settings)
    if provider == "mock":
        dimensions = int(getattr(settings, "MOCK_EMBEDDING_DIMENSIONS", 384))
        return MockEmbeddingProvider(dimensions=dimensions)
    raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {provider}")
