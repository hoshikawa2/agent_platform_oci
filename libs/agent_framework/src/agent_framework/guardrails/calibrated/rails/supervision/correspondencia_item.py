"""CorrespondenciaItemRail — supervisão de correspondência entre item reclamado e cancelado.

Detecta quando o item cancelado é uma variante premium ou tem valor superior
ao item que o cliente mencionou ou reclamou.

Caso típico: cliente reclama de "TIM Music" (R$ 9,90) mas o agente cancela
"TIM Music Premium" (R$ 19,90) — dano ao cliente por cancelamento errado.

Implementa o Protocol ``Rail`` de contracts.py (AT-06.2).
"""
from __future__ import annotations

import json
import logging

from ...contracts import GuardRailContext, GuardRailLLMClient, RailDecision
from ...llm_adapter import AgentLLMClientAdapter
from ...prompts.fallback import _REGEN_FLAG_BY_CODE
from ...prompts.shared.supervision_template import build_supervision_prompt

logger = logging.getLogger(__name__)

_CRITERIOS = """\
1. O nome do item cancelado é diferente do nome do item que o cliente mencionou, \
especialmente quando a diferença indica variante premium ("Plus", "Premium", "Max").
2. O valor do item cancelado é maior que o valor que o cliente mencionou ou reclamou.
3. O item cancelado pertence a uma categoria diferente do item reclamado pelo cliente.
4. Correspondência parcial de nome (ex.: "TIM Music" vs "TIM Music Premium") \
NÃO é suficiente — verificar valor e variante.
5. Se os valores e nomes correspondem adequadamente, NÃO é violação."""

_EXEMPLOS = """\
Exemplo 1 — VIOLAÇÃO:
  Dados: {"item_mencionado_cliente": "TIM Music", "item_cancelado": "TIM Music Premium", \
"valor_mencionado": 9.90, "valor_cancelado": 19.90}
  Saída: {"violation": true, "confidence": "high", "reason": "Cancelado TIM Music Premium (R$19,90) mas cliente reclamou do TIM Music (R$9,90)"}

Exemplo 2 — VIOLAÇÃO:
  Dados: {"item_mencionado_cliente": "Proteção de Tela", "item_cancelado": "Proteção Total Plus", \
"valor_mencionado": 5.99, "valor_cancelado": 14.99}
  Saída: {"violation": true, "confidence": "high", "reason": "Item cancelado é variante premium com valor R$9 acima do item reclamado"}

Exemplo 3 — NÃO VIOLAÇÃO:
  Dados: {"item_mencionado_cliente": "TIM Music", "item_cancelado": "TIM Music", \
"valor_mencionado": 9.90, "valor_cancelado": 9.90}
  Saída: {"violation": false, "confidence": "high", "reason": "Item e valor cancelados correspondem exatamente ao reclamado"}

Exemplo 4 — NÃO VIOLAÇÃO:
  Dados: {"item_mencionado_cliente": "serviço de streaming", "item_cancelado": "TIM Music", \
"valor_mencionado": 9.90, "valor_cancelado": 9.90}
  Saída: {"violation": false, "confidence": "medium", "reason": "Descrição genérica do cliente corresponde ao item cancelado com mesmo valor"}

Exemplo 5 — VIOLAÇÃO:
  Dados: {"item_mencionado_cliente": "antivírus", "item_cancelado": "TIM Segurança Digital Premium", \
"valor_mencionado": 4.99, "valor_cancelado": 12.99}
  Saída: {"violation": true, "confidence": "high", "reason": "Item cancelado é premium com valor 2,6x maior que o mencionado pelo cliente"}"""


class CorrespondenciaItemRail:
    """Rail de supervisão: correspondência entre item reclamado e item cancelado (AT-06.2).

    ``agent_metadata`` esperado:
        - ``item_mencionado_cliente`` (str): nome do item que o cliente reclamou.
        - ``item_cancelado`` (str): nome do item efetivamente cancelado.
        - ``valor_mencionado`` (float): valor que o cliente mencionou.
        - ``valor_cancelado`` (float): valor do item cancelado.

    Fallback conservador: em caso de falha técnica, retorna ``violation=False``.
    """

    def __init__(self, llm_client: GuardRailLLMClient | None = None) -> None:
        self._client: GuardRailLLMClient = llm_client or AgentLLMClientAdapter()

    @property
    def code(self) -> str:
        return "CORRESPONDENCIA_ITEM"

    @property
    def fallback_text(self) -> str | None:
        from ...pipeline import _FALLBACK_BY_CODE
        return _FALLBACK_BY_CODE.get("CORRESPONDENCIA_ITEM")

    @property
    def regen_flag(self) -> str | None:
        from ...prompts.fallback import _REGEN_FLAG_BY_CODE
        return _REGEN_FLAG_BY_CODE.get("CORRESPONDENCIA_ITEM")

    @property
    def is_soft_alert(self) -> bool:
        return False

    def evaluate(self, context: GuardRailContext) -> RailDecision:
        """Avalia correspondência entre item mencionado e item cancelado.

        Args:
            context: GuardRailContext com:
                - ``user_text``: última fala do agente (output a supervisionar).
                - ``conversation_history``: histórico recente da conversa.
                - ``agent_metadata``: ``{"item_mencionado_cliente": str,
                  "item_cancelado": str, "valor_mencionado": float,
                  "valor_cancelado": float}``.

        Returns:
            RailDecision com ``allowed=False`` quando violação detectada;
            ``allowed=True`` caso contrário ou em falha técnica.
        """
        meta = context.agent_metadata or {}
        historico_formatado = _format_history(context.conversation_history)
        dados_transacao = json.dumps(
            {
                "item_mencionado_cliente": meta.get("item_mencionado_cliente", ""),
                "item_cancelado": meta.get("item_cancelado", ""),
                "valor_mencionado": meta.get("valor_mencionado"),
                "valor_cancelado": meta.get("valor_cancelado"),
                "resposta_agente": context.user_text,
            },
            ensure_ascii=False,
        )

        prompt = build_supervision_prompt(
            rail_name="Correspondência de Item",
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
                "correspondencia_item_rail.invoke_error session=%s exc=%r — assuming no violation",
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
                "correspondencia_item_rail.violation session=%s confidence=%r reason=%r",
                context.session_id,
                confidence,
                reason,
            )
            return RailDecision(
                allowed=False,
                code=self.code,
                reason=reason,
                is_soft_alert=False,
                regen_flag=_REGEN_FLAG_BY_CODE.get("CORRESPONDENCIA_ITEM", ""),
            )

        return RailDecision(
            allowed=True,
            code=self.code,
            reason=reason,
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


__all__ = ["CorrespondenciaItemRail"]
