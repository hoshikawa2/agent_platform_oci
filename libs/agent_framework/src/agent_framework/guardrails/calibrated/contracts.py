"""Contratos centrais do sistema de guardrails TIM.

Define as abstrações de dados e protocolos que permitem desacoplar
implementações de rails, clientes LLM e o pipeline de orquestração.

- GuardRailContext: dados de entrada que todo rail recebe.
- RailDecision: decisão final do pipeline (re-exportada de pipeline.py
  no futuro; por ora definida aqui para uso pelos novos rails).
- Rail: Protocol que todo rail deve implementar.
- GuardRailLLMClient: Protocol para clientes LLM usados pelos rails.
- GuardRailEvent: evento de telemetria emitido por rail executado.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Contexto de execução
# ---------------------------------------------------------------------------

@dataclass
class GuardRailContext:
    """Dados de contexto que o pipeline passa a cada rail.

    Campos:
        session_id: identificador da sessão de atendimento.
        user_text: texto do usuário (input) ou do agente (output) a avaliar.
        conversation_history: histórico recente no formato
            [{"role": "user"|"assistant", "content": str}, ...].
        agent_metadata: metadados arbitrários do agente (tipo_fluxo,
            expected_protocols, msisdn, etc.).
    """
    session_id: str
    user_text: str
    conversation_history: list[dict] = field(default_factory=list)
    agent_metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Decisão de rail (espelho do RailDecision em pipeline.py)
# ---------------------------------------------------------------------------

@dataclass
class RailDecision:
    """Resultado de avaliação de um rail individual.

    Mantido aqui para que rails novos em guardrails/rails/ possam importar
    sem depender de pipeline.py (que importa tudo da infra). pipeline.py
    continuará definindo seu próprio RailDecision até a migração completa;
    os dois são estruturalmente idênticos e intercambiáveis.

    Campos:
        allowed: True quando o rail aprova a mensagem.
        code: código do rail que gerou a decisão (ex.: "PINJ", "OOS").
        reason: explicação legível da decisão.
        fallback_text: texto substituto quando allowed=False.
        sanitized_text: texto transformado quando o rail faz sanitização.
        is_soft_alert: distingue hard-block de soft-alert.
            False (default) = hard-block: substituir result["content"] e patchar
            histórico quando allowed=False.
            True = soft-alert: logar a violação sem alterar a resposta ao cliente
            (allowed é ignorado pelo pipeline neste caso).
        regen_flag: flag corretiva para re-invocar o agente principal com
            constraint adicional de contexto. None indica que o rail não
            suporta regeneração e o pipeline deve usar apenas o fallback
            estático (_FALLBACK_BY_CODE). String não-vazia é injetada como
            mensagem de correção no histórico antes de re-invocar o agente.
    """
    allowed: bool
    code: str | None = None
    reason: str = ""
    fallback_text: str | None = None
    sanitized_text: str | None = None
    # Distingue hard-block (substitui resposta) de soft-alert (apenas loga).
    # False = default = hard-block: substituir result["content"] + patchar histórico.
    # True = soft-alert: logar violação, não alterar a resposta ao cliente.
    is_soft_alert: bool = False
    # Flag corretiva para re-invocar o agente principal com constraint.
    # None = rail não suporta regeneração (usa apenas fallback estático).
    regen_flag: str | None = None


# ---------------------------------------------------------------------------
# Protocolos
# ---------------------------------------------------------------------------

@runtime_checkable
class Rail(Protocol):
    """Protocolo que todo rail deve implementar.

    Propriedades:
        code: identificador do rail (ex.: "PINJ", "CMP", "ANATEL").
        fallback_text: texto de fallback estático; None = rail não é hard-blocking.
        regen_flag: flag corretiva para regeneração; None = sem regeneração.
        is_soft_alert: True = violação apenas logada; False (default) = hard-block.

    Métodos:
        evaluate: avalia o contexto e devolve uma RailDecision.
    """

    @property
    def code(self) -> str:
        ...

    @property
    def fallback_text(self) -> str | None:
        """Texto de fallback estático. None = rail não é hard-blocking."""
        return None

    @property
    def regen_flag(self) -> str | None:
        """Flag corretiva para regeneração do agente. None = sem regeneração."""
        return None

    @property
    def is_soft_alert(self) -> bool:
        """True = violação apenas logada. False (default) = hard-block."""
        return False

    def evaluate(self, context: GuardRailContext) -> RailDecision:
        ...


@runtime_checkable
class GuardRailLLMClient(Protocol):
    """Protocolo para clientes LLM usados pelos rails.

    Método:
        invoke: executa uma capability identificada por `capability_id`
            com as variáveis de `input_vars` e retorna a resposta como str
            (texto bruto do LLM, antes de qualquer parse JSON).
    """

    def invoke(self, capability_id: str, input_vars: dict[str, Any]) -> str:
        ...


# ---------------------------------------------------------------------------
# Evento de telemetria
# ---------------------------------------------------------------------------

@dataclass
class GuardRailEvent:
    """Evento emitido após a execução de um rail, para telemetria / auditoria.

    Campos:
        session_id: identificador da sessão.
        rail_code: código do rail (ex.: "PINJ", "OOS", "CMP").
        allowed: resultado da avaliação.
        reason: explicação legível da decisão.
        latency_ms: tempo de execução do rail em milissegundos.
    """
    session_id: str
    rail_code: str
    allowed: bool
    reason: str
    latency_ms: float


__all__ = [
    "GuardRailContext",
    "RailDecision",
    "Rail",
    "GuardRailLLMClient",
    "GuardRailEvent",
]
