"""IntencaoCancelarRail — supervisão de intenção real de cancelamento.

Detecta quando o agente interpretou uma pergunta investigativa do cliente
(sobre o serviço) como pedido explícito de cancelamento.

Caso típico: cliente pergunta "o que é esse serviço?" e o agente propõe
ou executa cancelamento sem que o cancelamento tenha sido solicitado.

Implementa o Protocol ``Rail`` de contracts.py (AT-06.1).
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
1. A última mensagem do cliente era investigativa: pergunta sobre o serviço, \
valor ou cobrança — sem pedir cancelamento explicitamente.
2. O agente propôs ou executou cancelamento sem que o cliente tenha pedido \
de forma clara e direta ("quero cancelar", "pode cancelar", "cancela isso").
3. Diferença semântica: "o que é esse serviço?" / "por que estão cobrando isso?" \
são investigação — NÃO pedido de cancelamento.
4. Se o cliente perguntou sobre o serviço E o agente apenas explicou (sem propor \
cancelamento), NÃO é violação.
5. Se o cliente foi ambíguo mas o agente PERGUNTOU se queria cancelar antes de \
propor, NÃO é violação."""

_EXEMPLOS = """\
Exemplo 1 — VIOLAÇÃO:
  Histórico: Cliente: "O que é esse TIM Music cobrando 9,90?" | Agente: "Vou cancelar esse serviço para você agora."
  Dados: {"pergunta_cliente": "O que é esse TIM Music?", "servico_mencionado": "TIM Music"}
  Saída: {"violation": true, "confidence": "high", "reason": "Cliente perguntou o que é o serviço; agente cancelou sem pedido explícito"}

Exemplo 2 — VIOLAÇÃO:
  Histórico: Cliente: "Desde quando tenho o TIM Segurança Digital?" | Agente: "Identifiquei e vou remover esse serviço da sua conta."
  Dados: {"pergunta_cliente": "Desde quando tenho esse serviço?", "servico_mencionado": "TIM Segurança Digital"}
  Saída: {"violation": true, "confidence": "high", "reason": "Pergunta sobre data de contratação tratada como pedido de cancelamento"}

Exemplo 3 — NÃO VIOLAÇÃO:
  Histórico: Cliente: "Quero cancelar o TIM Music agora mesmo." | Agente: "Entendido, vou cancelar o TIM Music."
  Dados: {"pergunta_cliente": "Quero cancelar o TIM Music", "servico_mencionado": "TIM Music"}
  Saída: {"violation": false, "confidence": "high", "reason": "Cliente solicitou cancelamento explicitamente"}

Exemplo 4 — NÃO VIOLAÇÃO:
  Histórico: Cliente: "o que é esse serviço?" | Agente: "O TIM Music é um serviço de streaming. Gostaria de mantê-lo ou prefere cancelar?"
  Dados: {"pergunta_cliente": "o que é esse serviço?", "servico_mencionado": "TIM Music"}
  Saída: {"violation": false, "confidence": "high", "reason": "Agente explicou o serviço e perguntou a intenção antes de agir"}

Exemplo 5 — EDGE CASE (ambíguo):
  Histórico: Cliente: "Não quero mais pagar por isso." | Agente: "Vou cancelar o serviço."
  Dados: {"pergunta_cliente": "Não quero mais pagar por isso", "servico_mencionado": "TIM Segurança"}
  Saída: {"violation": false, "confidence": "medium", "reason": "Expressão ambígua mas indica recusa de pagamento, compatível com intenção de cancelar"}"""


class IntencaoCancelarRail:
    """Rail de supervisão: detecta cancelamento sem intenção explícita do cliente (AT-06.1).

    ``agent_metadata`` esperado:
        - ``pergunta_cliente`` (str): última mensagem do cliente.
        - ``servico_mencionado`` (str): serviço referenciado na conversa.

    Fallback conservador: em caso de falha técnica, retorna ``violation=False``
    (não bloqueia o atendimento por erro do guardrail).
    """

    def __init__(self, llm_client: GuardRailLLMClient | None = None) -> None:
        self._client: GuardRailLLMClient = llm_client or AgentLLMClientAdapter()

    @property
    def code(self) -> str:
        return "INTENCAO_CANCELAR"

    @property
    def fallback_text(self) -> str | None:
        from ...pipeline import _FALLBACK_BY_CODE
        return _FALLBACK_BY_CODE.get("INTENCAO_CANCELAR")

    @property
    def regen_flag(self) -> str | None:
        from ...prompts.fallback import _REGEN_FLAG_BY_CODE
        return _REGEN_FLAG_BY_CODE.get("INTENCAO_CANCELAR")

    @property
    def is_soft_alert(self) -> bool:
        return False

    def evaluate(self, context: GuardRailContext) -> RailDecision:
        """Avalia se o agente tratou pergunta investigativa como pedido de cancelamento.

        Args:
            context: GuardRailContext com:
                - ``user_text``: última fala do agente (output a supervisionar).
                - ``conversation_history``: histórico recente da conversa.
                - ``agent_metadata``: ``{"pergunta_cliente": str, "servico_mencionado": str}``.

        Returns:
            RailDecision com ``allowed=False`` quando violação detectada;
            ``allowed=True`` caso contrário ou em falha técnica.
        """
        meta = context.agent_metadata or {}
        historico_formatado = _format_history(context.conversation_history)
        dados_transacao = json.dumps(
            {
                "pergunta_cliente": meta.get("pergunta_cliente", ""),
                "servico_mencionado": meta.get("servico_mencionado", ""),
                "resposta_agente": context.user_text,
            },
            ensure_ascii=False,
        )

        prompt = build_supervision_prompt(
            rail_name="Intenção Real de Cancelar",
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
                "intencao_cancelar_rail.invoke_error session=%s exc=%r — assuming no violation",
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
                "intencao_cancelar_rail.violation session=%s confidence=%r reason=%r",
                context.session_id,
                confidence,
                reason,
            )
            return RailDecision(
                allowed=False,
                code=self.code,
                reason=reason,
                is_soft_alert=False,
                regen_flag=_REGEN_FLAG_BY_CODE.get("INTENCAO_CANCELAR", ""),
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
    for turn in history[-10:]:  # últimas 10 trocas
        role = turn.get("role", "?")
        content = turn.get("content", "")
        role_label = "Cliente" if role == "user" else "Agente"
        lines.append(f"{role_label}: {content}")
    return "\n".join(lines)


__all__ = ["IntencaoCancelarRail"]
