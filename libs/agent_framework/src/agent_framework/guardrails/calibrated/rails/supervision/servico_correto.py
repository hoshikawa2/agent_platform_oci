"""ServiceCorreto — supervisão de associação técnica de VAS correta.

Detecta quando o sistema escolheu o VAS (Value Added Service) errado entre
candidatos com nomes parecidos — o serviço tecnicamente cancelado não é o
serviço que o cliente reclamou.

Caso típico: cliente reclamou de "TIM Music" mas o sistema cancelou
"TIM Música Ilimitada" (outro VAS com ID diferente).

Implementa o Protocol ``Rail`` de contracts.py (AT-06.6).
"""
from __future__ import annotations

import json
import logging

from ...contracts import GuardRailContext, GuardRailLLMClient, RailDecision
from ...llm_adapter import AgentLLMClientAdapter
from ...prompts.shared.supervision_template import build_supervision_prompt

logger = logging.getLogger(__name__)

_CRITERIOS = """\
1. O ID do serviço cancelado no sistema não corresponde ao serviço que o \
cliente descreveu ou reclamou pelo nome.
2. Existem múltiplos VAS com nomes parecidos e o sistema pode ter associado \
o errado (ex.: "TIM Music" vs "TIM Música Ilimitada" — IDs diferentes).
3. O serviço cancelado pertence a uma categoria técnica diferente da categoria \
que o cliente mencionou (ex.: cliente reclamou de streaming, foi cancelado antivírus).
4. Se o nome do serviço cancelado e o serviço reclamado são equivalentes \
semânticos claros, NÃO é violação mesmo com nomes ligeiramente diferentes.
5. Diferenças apenas de maiúsculas, acentuação ou abreviação do mesmo serviço \
NÃO são violação."""

_EXEMPLOS = """\
Exemplo 1 — VIOLAÇÃO:
  Dados: {"servico_reclamado": "TIM Music", "servico_cancelado_id": "VAS_MUSIC_ILT", \
"servico_cancelado_nome": "TIM Música Ilimitada"}
  Saída: {"violation": true, "confidence": "high", "reason": "Cliente reclamou de TIM Music mas foi cancelado TIM Música Ilimitada (ID diferente)"}

Exemplo 2 — VIOLAÇÃO:
  Dados: {"servico_reclamado": "antivírus", "servico_cancelado_id": "VAS_MUSIC_PREM", \
"servico_cancelado_nome": "TIM Music Premium"}
  Saída: {"violation": true, "confidence": "high", "reason": "Cliente reclamou de antivírus; foi cancelado serviço de streaming musical"}

Exemplo 3 — NÃO VIOLAÇÃO:
  Dados: {"servico_reclamado": "TIM Music", "servico_cancelado_id": "VAS_TIM_MUSIC", \
"servico_cancelado_nome": "TIM Music"}
  Saída: {"violation": false, "confidence": "high", "reason": "ID e nome do serviço cancelado correspondem ao reclamado"}

Exemplo 4 — NÃO VIOLAÇÃO:
  Dados: {"servico_reclamado": "serviço de música", "servico_cancelado_id": "VAS_TIM_MUSIC", \
"servico_cancelado_nome": "TIM Music"}
  Saída: {"violation": false, "confidence": "medium", "reason": "Descrição genérica do cliente é compatível com o serviço TIM Music cancelado"}

Exemplo 5 — VIOLAÇÃO:
  Dados: {"servico_reclamado": "Proteção de Tela", "servico_cancelado_id": "VAS_SEG_DIG", \
"servico_cancelado_nome": "TIM Segurança Digital"}
  Saída: {"violation": true, "confidence": "high", "reason": "Cliente reclamou de proteção de tela física; foi cancelado serviço de segurança digital (categoria diferente)"}"""


class ServicoCorrretoRail:
    """Rail de supervisão: serviço técnico cancelado corresponde ao reclamado (AT-06.6).

    ``agent_metadata`` esperado:
        - ``servico_reclamado`` (str): nome/descrição do serviço que o cliente reclamou.
        - ``servico_cancelado_id`` (str): ID técnico do VAS efetivamente cancelado.
        - ``servico_cancelado_nome`` (str): nome do VAS efetivamente cancelado.

    Fallback conservador: em caso de falha técnica, retorna ``violation=False``.
    """

    def __init__(self, llm_client: GuardRailLLMClient | None = None) -> None:
        self._client: GuardRailLLMClient = llm_client or AgentLLMClientAdapter()

    @property
    def code(self) -> str:
        return "SERVICO_CORRETO"

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
        """Avalia se o serviço tecnicamente cancelado corresponde ao reclamado.

        Args:
            context: GuardRailContext com:
                - ``user_text``: última fala do agente (output a supervisionar).
                - ``conversation_history``: histórico recente da conversa.
                - ``agent_metadata``: ``{"servico_reclamado": str,
                  "servico_cancelado_id": str, "servico_cancelado_nome": str}``.

        Returns:
            RailDecision com ``allowed=False`` quando serviço errado detectado;
            ``allowed=True`` caso contrário ou em falha técnica.
        """
        meta = context.agent_metadata or {}
        historico_formatado = _format_history(context.conversation_history)
        dados_transacao = json.dumps(
            {
                "servico_reclamado": meta.get("servico_reclamado", ""),
                "servico_cancelado_id": meta.get("servico_cancelado_id", ""),
                "servico_cancelado_nome": meta.get("servico_cancelado_nome", ""),
                "resposta_agente": context.user_text,
            },
            ensure_ascii=False,
        )

        prompt = build_supervision_prompt(
            rail_name="Serviço Correto",
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
                "servico_correto_rail.invoke_error session=%s exc=%r — assuming no violation",
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
                "servico_correto_rail.violation session=%s confidence=%r reason=%r",
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


__all__ = ["ServicoCorrretoRail"]
