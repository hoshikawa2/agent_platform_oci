"""QuantidadeCoerente — supervisão de quantidade de itens cancelados vs. reclamados.

Detecta quando a quantidade de itens cancelados difere significativamente
da quantidade de itens que o cliente mencionou na conversa.

Caso típico: cliente reclamou de 1 serviço mas o agente cancelou 3 —
ou cliente mencionou "esse serviço" e o agente cancelou todos os VAS.

Implementa o Protocol ``Rail`` de contracts.py (AT-06.3).
"""
from __future__ import annotations

import json
import logging

from ...contracts import GuardRailContext, GuardRailLLMClient, RailDecision
from ...llm_adapter import AgentLLMClientAdapter
from ...prompts.shared.supervision_template import build_supervision_prompt

logger = logging.getLogger(__name__)

_CRITERIOS = """\
1. Quantidade de itens cancelados difere significativamente da quantidade \
que o cliente mencionou (diferença > 0 quando o cliente foi específico).
2. Os itens cancelados incluem serviços que o cliente NÃO mencionou em \
nenhum momento do histórico da conversa.
3. Analisar o histórico completo para identificar quantos itens o cliente \
efetivamente reclamou ou pediu para cancelar.
4. Referências genéricas como "esses serviços" ou "tudo isso" após listar \
múltiplos itens NÃO são violação se o cliente os listou explicitamente.
5. Se a quantidade cancelada for maior que a mencionada SEM autorização \
explícita para o excedente, É violação."""

_EXEMPLOS = """\
Exemplo 1 — VIOLAÇÃO:
  Histórico: Cliente: "quero cancelar o TIM Music"
  Dados: {"quantidade_mencionada": 1, "quantidade_cancelada": 3, \
"itens_cancelados": ["TIM Music", "TIM Segurança Digital", "Proteção de Tela"]}
  Saída: {"violation": true, "confidence": "high", "reason": "Cliente mencionou 1 serviço, mas 3 foram cancelados sem autorização"}

Exemplo 2 — VIOLAÇÃO:
  Histórico: Cliente: "cancela o TIM Music e o TIM Segurança"
  Dados: {"quantidade_mencionada": 2, "quantidade_cancelada": 5, \
"itens_cancelados": ["TIM Music", "TIM Segurança", "Proteção Plus", "TIM Banca", "TIM Notícias"]}
  Saída: {"violation": true, "confidence": "high", "reason": "Cliente autorizou 2 cancelamentos; 3 itens extras foram cancelados sem pedido"}

Exemplo 3 — NÃO VIOLAÇÃO:
  Histórico: Cliente: "quero cancelar TIM Music, TIM Segurança e Proteção de Tela"
  Dados: {"quantidade_mencionada": 3, "quantidade_cancelada": 3, \
"itens_cancelados": ["TIM Music", "TIM Segurança", "Proteção de Tela"]}
  Saída: {"violation": false, "confidence": "high", "reason": "Quantidade cancelada corresponde exatamente ao solicitado"}

Exemplo 4 — NÃO VIOLAÇÃO:
  Histórico: Cliente: "cancela tudo que eu não pedi, esses serviços todos que aparecem aqui"
  Dados: {"quantidade_mencionada": 4, "quantidade_cancelada": 4, \
"itens_cancelados": ["TIM Music", "TIM Segurança", "Proteção Plus", "TIM Banca"]}
  Saída: {"violation": false, "confidence": "medium", "reason": "Cliente autorizou cancelamento de todos os VAS listados"}

Exemplo 5 — VIOLAÇÃO:
  Histórico: Cliente: "cancela esse serviço de música"
  Dados: {"quantidade_mencionada": 1, "quantidade_cancelada": 2, \
"itens_cancelados": ["TIM Music", "TIM Music Premium"]}
  Saída: {"violation": true, "confidence": "high", "reason": "Cliente mencionou 1 serviço de música; 2 variantes foram canceladas sem pedido explícito"}"""


class QuantidadeCoerente:
    """Rail de supervisão: coerência entre quantidade mencionada e cancelada (AT-06.3).

    ``agent_metadata`` esperado:
        - ``quantidade_mencionada`` (int): quantidade de itens mencionados pelo cliente.
        - ``quantidade_cancelada`` (int): quantidade de itens efetivamente cancelados.
        - ``itens_cancelados`` (list[str]): nomes dos itens cancelados.

    Fallback conservador: em caso de falha técnica, retorna ``violation=False``.
    """

    def __init__(self, llm_client: GuardRailLLMClient | None = None) -> None:
        self._client: GuardRailLLMClient = llm_client or AgentLLMClientAdapter()

    @property
    def code(self) -> str:
        return "QUANTIDADE_COERENTE"

    @property
    def fallback_text(self) -> str | None:
        return None

    @property
    def regen_flag(self) -> str | None:
        return None

    @property
    def is_soft_alert(self) -> bool:
        return True

    def evaluate(self, context: GuardRailContext) -> RailDecision:
        """Avalia coerência entre quantidade de itens mencionados e cancelados.

        Args:
            context: GuardRailContext com:
                - ``user_text``: última fala do agente (output a supervisionar).
                - ``conversation_history``: histórico recente da conversa.
                - ``agent_metadata``: ``{"quantidade_mencionada": int,
                  "quantidade_cancelada": int, "itens_cancelados": list[str]}``.

        Returns:
            RailDecision com ``allowed=False`` quando violação detectada;
            ``allowed=True`` caso contrário ou em falha técnica.
        """
        meta = context.agent_metadata or {}
        historico_formatado = _format_history(context.conversation_history)
        dados_transacao = json.dumps(
            {
                "quantidade_mencionada": meta.get("quantidade_mencionada"),
                "quantidade_cancelada": meta.get("quantidade_cancelada"),
                "itens_cancelados": meta.get("itens_cancelados", []),
                "resposta_agente": context.user_text,
            },
            ensure_ascii=False,
        )

        prompt = build_supervision_prompt(
            rail_name="Quantidade Coerente de Cancelamentos",
            criterios=_CRITERIOS,
            historico=historico_formatado,
            dados_transacao=dados_transacao,
            exemplos=_EXEMPLOS,
        )

        input_vars = {
            "text": context.user_text,
            "prompt": prompt,
            "context": meta,
        }

        try:
            raw = self._client.invoke(self.code, input_vars)
            result: dict = json.loads(raw) if isinstance(raw, str) else raw
        except Exception as exc:
            logger.error(
                "quantidade_coerente_rail.invoke_error session=%s exc=%r — assuming no violation",
                context.session_id,
                exc,
            )
            return RailDecision(
                allowed=True,
                code=self.code,
                reason="evaluation_error",
            )

        violation = bool(result.get("violation", False))
        reason = result.get("reason", "")
        confidence = result.get("confidence", "")

        if violation:
            logger.warning(
                "quantidade_coerente_rail.violation session=%s confidence=%r reason=%r",
                context.session_id,
                confidence,
                reason,
            )
            return RailDecision(
                allowed=True,
                is_soft_alert=True,
                code=self.code,
                reason=reason,
            )

        return RailDecision(
            allowed=True,
            code=self.code,
            reason="no_violation",
        )


def _format_history(history: list[dict]) -> str:
    """Formata o histórico de conversa para inserção no prompt."""
    if not history:
        return "(sem histórico disponível)"
    lines = []
    for turn in history[-10:]:
        role = turn.get("role", "?")
        content = turn.get("content", "")
        role_label = "Cliente" if role == "user" else "Agente"
        lines.append(f"{role_label}: {content}")
    return "\n".join(lines)


__all__ = ["QuantidadeCoerente"]
