from __future__ import annotations

from typing import Any


class NOCReasoningAdvisor:
    """Optional LLM advisor for NOC diagnostics using profile `noc`."""

    def __init__(self, llm: Any, *, profile_name: str = "noc"):
        self.llm = llm
        self.profile_name = profile_name

    async def analyze(self, event: dict[str, Any], context: dict[str, Any] | None = None) -> str:
        if not self.llm:
            return ""
        return await self.llm.ainvoke(
            [
                {"role": "system", "content": "Você analisa eventos NOC e sugere diagnóstico operacional de forma objetiva."},
                {"role": "user", "content": f"Evento NOC:\n{event}\n\nContexto:\n{context or {}}"},
            ],
            temperature=0,
            profile_name=self.profile_name,
            component_name=self.profile_name,
            generation_name=f"llm.{self.profile_name}",
        )


class GRLReasoningAdvisor:
    """Optional LLM advisor for GRL remediation using profile `grl`."""

    def __init__(self, llm: Any, *, profile_name: str = "grl"):
        self.llm = llm
        self.profile_name = profile_name

    async def suggest(self, candidate: str, guardrail_results: list[Any], context: dict[str, Any] | None = None) -> str:
        if not self.llm:
            return ""
        return await self.llm.ainvoke(
            [
                {"role": "system", "content": "Você sugere correções seguras para respostas reprovadas por guardrails."},
                {"role": "user", "content": f"Resposta candidata:\n{candidate}\n\nResultados GRL:\n{guardrail_results}\n\nContexto:\n{context or {}}"},
            ],
            temperature=0,
            profile_name=self.profile_name,
            component_name=self.profile_name,
            generation_name=f"llm.{self.profile_name}",
        )
