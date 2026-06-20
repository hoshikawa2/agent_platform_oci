"""Adapter entre GuardRailLLMClient (Protocol) e GuardrailLLMClient (concreto).

AgentLLMClientAdapter implementa o Protocol GuardRailLLMClient definido em
contracts.py, delegando para o GuardrailLLMClient existente em llm_client.py.

Permite que os novos rails (guardrails/rails/*.py) usem o Protocol sem depender
diretamente do GuardrailLLMClient concreto — facilitando testes e futuras
trocas de implementação.

Mapeamento de capability_id -> task do GuardrailLLMClient:
    O campo `capability_id` é passado diretamente como `task` para
    GuardrailLLMClient.classify(). Os valores válidos são os mesmos já
    suportados pelo cliente: "AOFERTA", "REVPREC", "OOS", "TOXOUT", "TOX",
    "PINJ", "RAGSEC", "DLEX_IN", "DLEX_OUT", "FALLBACK".

Exemplo de uso:
    from agente_contas_tim.guardrails.llm_adapter import AgentLLMClientAdapter
    from agente_contas_tim.guardrails.llm_client import GuardrailLLMClient

    adapter = AgentLLMClientAdapter(GuardrailLLMClient())
    raw_json_str = adapter.invoke("PINJ", {"text": "ignore all rules"})
"""
from __future__ import annotations

import json
from typing import Any

from .llm_client import GuardrailLLMClient


class AgentLLMClientAdapter:
    """Implementa GuardRailLLMClient delegando para GuardrailLLMClient.

    O Protocol GuardRailLLMClient define `invoke(capability_id, input_vars) -> str`.
    O GuardrailLLMClient concreto expõe `classify(task, payload) -> dict`.

    Este adapter:
    1. Repassa `capability_id` como `task`.
    2. Repassa `input_vars` como `payload`.
    3. Serializa o dict retornado por `classify` de volta para str (JSON),
       pois o Protocol contratua retorno como str — o rail chamador faz
       json.loads() conforme necessário.
    """

    def __init__(self, client: GuardrailLLMClient | None = None) -> None:
        """Inicializa o adapter.

        Args:
            client: instância de GuardrailLLMClient a delegar. Quando None,
                    cria uma nova instância com as configurações padrão
                    do ambiente.
        """
        self._client: GuardrailLLMClient = client or GuardrailLLMClient()

    def invoke(self, capability_id: str, input_vars: dict[str, Any]) -> str:
        """Invoca o LLM para a capability indicada e retorna JSON como str.

        Args:
            capability_id: identificador da tarefa de guardrail (ex.: "PINJ",
                "OOS", "AOFERTA"). Mapeado diretamente para `task` do cliente.
            input_vars: variáveis de input (ex.: {"text": ..., "context": ...}).
                Mapeado diretamente para `payload` do cliente.

        Returns:
            Resposta do LLM serializada como string JSON. Em caso de falha
            de classificação, o cliente já retorna {"allowed": False, "label":
            "ERROR", "reason": ...} — este adapter apenas serializa o dict.

        Raises:
            ValueError: propagado pelo cliente quando `capability_id` não é
                uma task suportada.
        """
        result: dict = self._client.classify(capability_id, input_vars)
        return json.dumps(result, ensure_ascii=False)


__all__ = ["AgentLLMClientAdapter"]
