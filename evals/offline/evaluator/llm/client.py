from __future__ import annotations

import json
from typing import Any

from evaluator.config.settings import settings
from evaluator.llm.profile_resolver import LLMProfileResolver


class LLMClient:
    async def complete(self, prompt: str, profile_name: str | None = None) -> str:
        raise NotImplementedError


class MockLLMClient(LLMClient):
    async def complete(self, prompt: str, profile_name: str | None = None) -> str:
        if "inferredCsiScore" in prompt:
            return json.dumps({
                "inferredCsiScore": 0.5,
                "resolution": 1,
                "conversationPrecision": 1,
                "rationale": "Avaliação mock."
            }, ensure_ascii=False)

        return json.dumps({
            "judgeScore": 0.7,
            "accuracyScore": 0.7,
            "alucinationScore": 0.1,
            "rationale": "Avaliação mock."
        }, ensure_ascii=False)


class OCICompatibleLLMClient(LLMClient):
    """
    Mesmo padrão do Agent Framework:
    - LLM_PROVIDER=oci_openai
    - OCI_GENAI_BASE_URL
    - OCI_GENAI_API_KEY
    - OCI_GENAI_MODEL
    - llm_profiles.yaml opcional
    """

    def __init__(self):
        self.resolver = LLMProfileResolver(settings)

    async def complete(self, prompt: str, profile_name: str | None = None) -> str:
        effective = self.resolver.resolve(profile_name or settings.llm_profile)

        provider = str(effective.get("provider") or settings.LLM_PROVIDER)
        model = str(effective.get("model") or settings.OCI_GENAI_MODEL)
        base_url = effective.get("base_url") or settings.OCI_GENAI_BASE_URL
        api_key = effective.get("api_key") or settings.OCI_GENAI_API_KEY
        temperature = effective.get("temperature", settings.LLM_TEMPERATURE)
        max_tokens = effective.get("max_tokens", settings.LLM_MAX_TOKENS)
        timeout = effective.get("timeout_seconds", settings.LLM_TIMEOUT_SECONDS)

        if provider == "mock":
            return await MockLLMClient().complete(prompt, profile_name=profile_name)

        if provider not in ("oci_openai", "openai_compatible"):
            raise ValueError(f"Unsupported LLM provider: {provider}")

        if not base_url:
            raise RuntimeError("OCI_GENAI_BASE_URL is required for oci_openai provider")

        if not api_key:
            raise RuntimeError("OCI_GENAI_API_KEY is required for oci_openai provider")

        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
        )

        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return resp.choices[0].message.content or ""


def create_llm_client() -> LLMClient:
    provider = (settings.LLM_PROVIDER or "mock").lower()

    if provider in ("mock", "none"):
        return MockLLMClient()

    if provider in ("oci_openai", "openai_compatible", "oci"):
        return OCICompatibleLLMClient()

    raise ValueError(f"Unsupported LLM_PROVIDER={settings.LLM_PROVIDER}")