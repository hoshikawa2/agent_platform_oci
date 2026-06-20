"""ConfirmationRail — classifica se o cliente confirmou a ação proposta.

Migração de agent/infra/langchain/agent/execution/confirmation_classifier.py
para o novo padrão de Rail Protocol em guardrails/rails/.

Diferenças em relação ao original:
1. Usa GuardRailLLMClient.invoke() em vez de invoke_llm_with_config diretamente.
2. Adiciona try-except em torno de json.loads (COR-V5-003): falha de parse
   retorna fallback pessimista (confirmed=False, reason="parse_error").
3. O prompt inclui campo `reason` obrigatório na saída JSON:
   {"confirmed": true|false, "reason": "1 frase"} — alinhado com o
   padrão de todos os outros rails do pipeline.
4. Implementa o Protocol Rail de contracts.py, recebendo GuardRailContext.

O arquivo original em agent/infra/langchain/agent/execution/confirmation_classifier.py
NÃO foi alterado — este módulo é a nova implementação desacoplada.

Uso via Protocol Rail:
    from agente_contas_tim.guardrails.rails.confirmation import ConfirmationRail
    from ..contracts import GuardRailContext
    from ..llm_adapter import AgentLLMClientAdapter

    rail = ConfirmationRail(client=AgentLLMClientAdapter())
    ctx = GuardRailContext(
        session_id="abc",
        user_text="sim, pode cancelar",
        conversation_history=[
            {"role": "assistant", "content": "Posso seguir com o cancelamento do Tamboro?"},
        ],
        agent_metadata={"action_summary": "cancelar_vas_avulso (Tamboro)"},
    )
    decision = rail.evaluate(ctx)
    # decision.allowed == True  (cliente confirmou)

Uso via função standalone (compatibilidade):
    confirmed, reason = classify_confirmation(
        client=adapter,
        assistant_question="Posso seguir com o cancelamento?",
        user_response="sim",
        action_summary="cancelar_vas_avulso (Tamboro)",
    )
"""
from __future__ import annotations

import json
import logging
from typing import Any

from ..contracts import GuardRailContext, GuardRailLLMClient, RailDecision
from ..prompts.fallback import _REGEN_FLAG_BY_CODE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """Você é um classificador para um assistente de contas TIM.

Decida se a AÇÃO PROPOSTA (tool call: cancelamento, troca de plano,
reativação/ativação, ajuste de fatura, etc.) pode ser executada agora.
Responda confirmed=true só se AS DUAS condições forem verdadeiras:

(a) A pergunta do assistente no turno anterior pede concordância para a
    ação descrita em "Ação que será executada". Conta como tal:
    - pedidos diretos ("podemos seguir?", "você confirma?", "correto?",
      "está de acordo?") e equivalentes — não exija fraseologia específica;
    - recap do escopo + validação ("Entendi que você deseja X, Y, Z...
      Correto?"), quando os itens batem com os da ação;
    - descrição da RESOLUÇÃO/EFEITO no lugar do nome técnico da tool
      (ex.: "ajuste na fatura de R$X" em vez de "cancelar_vas_avulso").
    NÃO conta: perguntas genéricas de esclarecimento/fechamento que não
    restateiam a ação ("Consegui esclarecer sua dúvida?", "Posso ajudar
    com mais algo?"). Se (a) falhar, responda false sem analisar (b).

(b) A resposta do cliente concorda de forma CLARA com a ação.
    - CONFIRMA: concordância explícita ("sim", "pode", "confirmo", "ok",
      "pode seguir"), inclusive com justificativa que REFORÇA o pedido
      (ex.: "pode, eu não pedi isso", "sim, nunca usei").
    - NÃO confirma: contradição real — pede algo diferente, restringe
      escopo ("pode, mas só o X"), pausa ("espera, deixa eu pensar") ou
      reformula ("muda para Y"); ou nega sem nenhum "sim/pode" adjacente.

EXEMPLOS:
- P: "Posso seguir com o cancelamento do Tamboro, tudo bem?" / Ação: cancelar_vas_avulso (Tamboro) / C: "sim, pode cancelar" → {{"confirmed": true, "reason": "cliente confirmou explicitamente o cancelamento"}}
- P: "Entendi que você deseja os serviços AIA, EXA e Banca. Correto?" / Ação: vas_estrategico (AIA, EXA, Banca) / C: "sim" → {{"confirmed": true, "reason": "cliente confirmou recap da ação"}}
- P: "Posso cancelar Tamboro e YouTube?" / Ação: cancelar_vas_avulso (Tamboro, YouTube) / C: "pode, mas só o Tamboro" → {{"confirmed": false, "reason": "cliente restringiu escopo — apenas Tamboro"}}
- P: "Consegui esclarecer sua dúvida?" / Ação: cancelar_vas_avulso (Tim Fashion) / C: "sim, obrigado" → {{"confirmed": false, "reason": "pergunta do assistente não restateia a ação proposta"}}

---

Pergunta do assistente (turno imediatamente anterior):
{assistant_question}

Ação que será executada (tool_calls do agente):
{action_summary}

Resposta do cliente:
{user_response}

Responda APENAS JSON válido com os campos confirmed e reason:
{{"confirmed": true|false, "reason": "1 frase explicando a decisão"}}
"""


# ---------------------------------------------------------------------------
# Rail implementation
# ---------------------------------------------------------------------------

class ConfirmationRail:
    """Rail LLM que decide se o cliente confirmou a ação proposta.

    Implementa o Protocol Rail de contracts.py.

    O contexto esperado em GuardRailContext:
        user_text: resposta do cliente a ser classificada.
        conversation_history: último turno do assistente deve estar em
            conversation_history[-1] com role="assistant".
        agent_metadata: deve conter 'action_summary' (descrição da ação
            proposta pelo agente).

    Em caso de falha de parse do JSON retornado pelo LLM, aplica fallback
    pessimista: allowed=False, reason="parse_error — fallback pessimista".
    """

    def __init__(self, client: GuardRailLLMClient) -> None:
        """Inicializa o rail com o cliente LLM.

        Args:
            client: implementação do Protocol GuardRailLLMClient.
                    Tipicamente AgentLLMClientAdapter(GuardrailLLMClient()).
        """
        self._client = client

    @property
    def code(self) -> str:
        return "CONFIRM"

    @property
    def fallback_text(self) -> str | None:
        from ..pipeline import _FALLBACK_BY_CODE
        return _FALLBACK_BY_CODE.get("ACTION_CONFIRMATION_RETRY")

    @property
    def regen_flag(self) -> str | None:
        from ..prompts.fallback import _REGEN_FLAG_BY_CODE
        return _REGEN_FLAG_BY_CODE.get("ACTION_CONFIRMATION_RETRY")

    @property
    def is_soft_alert(self) -> bool:
        return False

    def evaluate(self, context: GuardRailContext) -> RailDecision:
        """Avalia se a resposta do cliente confirma a ação proposta.

        Args:
            context: GuardRailContext com user_text (resposta do cliente),
                conversation_history (turno anterior do assistente) e
                agent_metadata['action_summary'].

        Returns:
            RailDecision com:
                allowed=True  quando o cliente confirma claramente;
                allowed=False quando não confirma ou há falha de parse.
        """
        # Extrai pergunta do assistente do último turno do histórico
        assistant_question = ""
        for turn in reversed(context.conversation_history):
            if turn.get("role") == "assistant":
                assistant_question = turn.get("content", "")
                break

        action_summary = (context.agent_metadata or {}).get("action_summary", "")
        user_response = context.user_text

        confirmed, reason = classify_confirmation(
            client=self._client,
            assistant_question=assistant_question,
            user_response=user_response,
            action_summary=action_summary,
        )

        if not confirmed:
            return RailDecision(
                allowed=False,
                code="ACTION_CONFIRMATION_RETRY",
                reason=reason,
                is_soft_alert=False,
                regen_flag=_REGEN_FLAG_BY_CODE.get("ACTION_CONFIRMATION_RETRY", ""),
            )

        return RailDecision(
            allowed=True,
            code=self.code,
            reason=reason,
        )


# ---------------------------------------------------------------------------
# Função standalone (compatibilidade com callers que não usam Protocol Rail)
# ---------------------------------------------------------------------------

def classify_confirmation(
    client: GuardRailLLMClient,
    *,
    assistant_question: str,
    user_response: str,
    action_summary: str,
) -> tuple[bool, str]:
    """Classifica se a resposta do cliente confirma a ação proposta.

    Versão desacoplada do original em confirmation_classifier.py, usando
    o Protocol GuardRailLLMClient em vez de invoke_llm_with_config.

    Args:
        client: implementação do Protocol GuardRailLLMClient.
        assistant_question: pergunta do assistente no turno anterior.
        user_response: resposta do cliente a classificar.
        action_summary: descrição da ação que será executada.

    Returns:
        Tupla (confirmed: bool, reason: str).
        Em falha de parse ou exceção de LLM, retorna (False, "parse_error...").
        O fallback é pessimista: segurança > conveniência.
    """
    prompt = _PROMPT_TEMPLATE.format(
        assistant_question=assistant_question,
        action_summary=action_summary,
        user_response=user_response,
    )

    try:
        raw: str = client.invoke("CONFIRM", {"text": prompt, "context": {}})
    except Exception as exc:
        logger.warning(
            "confirmation_rail.invoke_failed error=%r — fallback pessimista",
            exc,
        )
        return False, f"invoke_error — fallback pessimista: {exc}"

    try:
        payload: dict[str, Any] = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning(
            "confirmation_rail.json_parse_failed raw=%r error=%r — fallback pessimista",
            raw[:200],
            exc,
        )
        return False, "parse_error — fallback pessimista"

    confirmed = bool(payload.get("confirmed", False))
    reason = str(payload.get("reason", ""))[:500]
    return confirmed, reason


__all__ = ["ConfirmationRail", "classify_confirmation"]
