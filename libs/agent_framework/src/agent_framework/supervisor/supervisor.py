from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SupervisorPlan:
    """Plano de execução para o modo supervisor.

    agents contém um ou mais agentes especialistas que devem ser chamados.
    Quando houver apenas um agente, o comportamento fica próximo ao EnterpriseRouter.
    Quando houver múltiplos agentes, o workflow executa os especialistas e consolida
    uma resposta única no nó supervisor_agent.
    """

    agents: list[str]
    intent: str
    confidence: float = 0.0
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class Supervisor:
    """Supervisor independente do agente.

    Use para duas finalidades:
    1. route_plan: decidir se a mensagem precisa de um ou vários agentes.
    2. review: revisar a resposta final consolidada antes de devolver ao canal.

    A implementação abaixo é determinística e simples de operar em ambiente
    corporativo. Em produção, ela pode ser substituída por uma versão LLM-based
    mantendo o mesmo contrato.
    """

    ROUTING_RULES: list[tuple[str, str, list[str]]] = [
        (
            "billing",
            "billing_agent",
            ["fatura", "conta", "cobrança", "cobranca", "boleto", "vencimento", "segunda via", "invoice"],
        ),
        (
            "product",
            "product_agent",
            ["produto", "plano", "oferta", "serviço", "servico", "pacote", "internet", "roaming", "vas"],
        ),
        (
            "orders",
            "orders_agent",
            ["pedido", "entrega", "rastreio", "rastreamento", "encomenda", "compra", "atraso", "correios"],
        ),
        (
            "support",
            "support_agent",
            ["troca", "devolução", "devolucao", "devolver", "garantia", "defeito", "quebrado", "suporte"],
        ),
    ]

    async def route(self, text: str, context: dict | None = None) -> str:
        """Compatibilidade com versões anteriores: retorna apenas um agente."""
        plan = await self.route_plan({"user_text": text, "context": context or {}})
        return plan.agents[0]

    async def route_plan(self, state: dict[str, Any]) -> SupervisorPlan:
        text = (state.get("sanitized_input") or state.get("user_text") or "").lower()
        selected: list[str] = []
        matched_intents: list[str] = []
        matched_keywords: dict[str, list[str]] = {}

        for intent, agent, keywords in self.ROUTING_RULES:
            hits = [kw for kw in keywords if kw in text]
            if hits:
                if agent not in selected:
                    selected.append(agent)
                matched_intents.append(intent)
                matched_keywords[agent] = hits

        if not selected:
            selected = ["billing_agent"]
            matched_intents = ["fallback"]

        multi = len(selected) > 1
        return SupervisorPlan(
            agents=selected,
            intent="multi_intent" if multi else matched_intents[0],
            confidence=0.9 if matched_keywords else 0.1,
            reason=(
                "Supervisor detectou múltiplas intenções e acionará mais de um agente."
                if multi
                else f"Supervisor selecionou {selected[0]}."
            ),
            metadata={"matched_keywords": matched_keywords, "multi_agent": multi},
        )

    async def review(self, answer: str, context: dict | None = None) -> tuple[bool, str]:
        if "atendente humano" in (answer or "").lower():
            return False, "Resposta bloqueada pelo supervisor: não direcionar para atendimento humano neste template."
        return True, answer
