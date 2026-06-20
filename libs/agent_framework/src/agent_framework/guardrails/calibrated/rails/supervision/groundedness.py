"""GroundednessRail — supervisão de aderência da resposta aos dados fornecidos.

Detecta quando a resposta do agente contém valores, datas ou fatos que
não estão presentes no invoice_detail ou nos chunks do RAG — isto é,
informações inventadas ou alucinadas pelo LLM.

Implementa o Protocol ``Rail`` de contracts.py (AT-06.4).
"""
from __future__ import annotations

import json
import logging

from ...contracts import GuardRailContext, GuardRailLLMClient, RailDecision
from ...llm_adapter import AgentLLMClientAdapter
from ...prompts.shared.supervision_template import build_supervision_prompt

logger = logging.getLogger(__name__)

_CRITERIOS = """\
1. A resposta menciona valores monetários específicos (ex.: "R$ 29,90") que \
NÃO aparecem nos dados do invoice_detail nem nos chunks do RAG.
2. A resposta afirma fatos sobre serviços, cobranças ou datas que NÃO estão \
nos chunks do RAG nem nos dados da fatura.
3. A resposta cita percentuais, descontos ou benefícios que NÃO constam nos \
dados fornecidos.
4. Se ``invoice_detail_presente=false``, aplicar groundedness apenas ao conteúdo \
dos chunks do RAG — ignorar ausência de dados da fatura.
5. Respostas genéricas de cortesia ou confirmação ("Entendido!", "Vou verificar.") \
NÃO precisam ser fundamentadas — NÃO são violação."""

_EXEMPLOS = """\
Exemplo 1 — VIOLAÇÃO:
  Resposta do agente: "O serviço TIM Music custa R$ 14,90 mensais na sua conta."
  Dados: {"invoice_detail_presente": true, "chunks_rag": ["TIM Music - R$ 9,90/mês"]}
  Saída: {"violation": true, "confidence": "high", "reason": "Agente informou R$14,90 mas o RAG indica R$9,90"}

Exemplo 2 — VIOLAÇÃO:
  Resposta do agente: "Você tem um desconto de 50% ativo no plano."
  Dados: {"invoice_detail_presente": true, "chunks_rag": ["Plano TIM Black - R$ 59,90/mês sem desconto"]}
  Saída: {"violation": true, "confidence": "high", "reason": "Agente mencionou desconto de 50% sem respaldo nos dados"}

Exemplo 3 — NÃO VIOLAÇÃO:
  Resposta do agente: "O TIM Music custa R$ 9,90 mensais conforme sua fatura."
  Dados: {"invoice_detail_presente": true, "chunks_rag": ["TIM Music - R$ 9,90/mês"]}
  Saída: {"violation": false, "confidence": "high", "reason": "Valor mencionado está presente nos dados do RAG"}

Exemplo 4 — NÃO VIOLAÇÃO (invoice ausente, RAG suficiente):
  Resposta do agente: "Esse serviço é o TIM Segurança Digital, um antivírus para smartphones."
  Dados: {"invoice_detail_presente": false, "chunks_rag": ["TIM Segurança Digital: antivírus para smartphones TIM"]}
  Saída: {"violation": false, "confidence": "high", "reason": "Descrição fundamentada no chunk do RAG; fatura ausente é esperado"}

Exemplo 5 — NÃO VIOLAÇÃO (resposta genérica):
  Resposta do agente: "Vou verificar as informações da sua conta agora."
  Dados: {"invoice_detail_presente": false, "chunks_rag": []}
  Saída: {"violation": false, "confidence": "high", "reason": "Resposta genérica de transição, não requer fundamentação em dados"}"""


class GroundednessRail:
    """Rail de supervisão: aderência da resposta aos dados fornecidos (AT-06.4).

    ``agent_metadata`` esperado:
        - ``invoice_detail_presente`` (bool): se dados da fatura estão disponíveis.
        - ``resposta_agente`` (str): resposta do agente a auditar (mesmo que user_text).
        - ``chunks_rag`` (list[str]): chunks recuperados pelo RAG.

    Fallback conservador: em caso de falha técnica, retorna ``violation=False``.
    """

    def __init__(self, llm_client: GuardRailLLMClient | None = None) -> None:
        self._client: GuardRailLLMClient = llm_client or AgentLLMClientAdapter()

    @property
    def code(self) -> str:
        return "GROUNDEDNESS"

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
        """Avalia se a resposta do agente está fundamentada nos dados disponíveis.

        Args:
            context: GuardRailContext com:
                - ``user_text``: resposta do agente a auditar.
                - ``conversation_history``: histórico recente da conversa.
                - ``agent_metadata``: ``{"invoice_detail_presente": bool,
                  "resposta_agente": str, "chunks_rag": list[str]}``.

        Returns:
            RailDecision com ``allowed=False`` quando alucinação detectada;
            ``allowed=True`` caso contrário ou em falha técnica.
        """
        meta = context.agent_metadata or {}
        historico_formatado = _format_history(context.conversation_history)
        dados_transacao = json.dumps(
            {
                "invoice_detail_presente": meta.get("invoice_detail_presente", False),
                "chunks_rag": meta.get("chunks_rag", []),
                "resposta_agente": meta.get("resposta_agente", context.user_text),
            },
            ensure_ascii=False,
        )

        prompt = build_supervision_prompt(
            rail_name="Groundedness",
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
                "groundedness_rail.invoke_error session=%s exc=%r — assuming no violation",
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
                "groundedness_rail.violation session=%s confidence=%r reason=%r",
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


__all__ = ["GroundednessRail"]
