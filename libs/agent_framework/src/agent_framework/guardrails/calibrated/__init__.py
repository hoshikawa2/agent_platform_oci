"""Guardrails de Supervisao TIM (extensao do agent_framework).

Padrao de uso:

    from agente_contas_tim.guardrails import (
        apply_input_rails,
        apply_output_rails,
        sanitizar_output,
    )

    # Input — MSK sanitiza PII e OOS bloqueia fora de escopo.
    in_decision = apply_input_rails(user_text)
    if not in_decision.allowed:
        return in_decision.fallback_text
    user_text = in_decision.sanitized_text or user_text

    result = agent.run(user_text=user_text)

    # Output sanitization (PII + toxicidade, sanitize-and-pass-through).
    sanitized = sanitizar_output(result["content"])
    result["content"] = sanitized.sanitized_text or result["content"]

    # Output rails bloqueantes.
    out_decision = apply_output_rails(
        text=result["content"],
        tool_calls=result.get("tool_calls"),
    )
    if not out_decision.allowed:
        result["content"] = out_decision.fallback_text  # AOFERTA ou REVPREC

Rails ativos:
- MSK — input/output sanitize; mascara PII antes do LLM e na resposta final.
- OOS — input rail; bloqueia mensagens fora do escopo de contas/faturas TIM.
- AOFERTA (extensao local) — output rail; supervisor LLM contra oferta proativa.
- REVPREC (extensao local) — output rail contra promessa operacional futura;
  prompt em prompts/revprec.py, routing via GuardrailLLMClient.
- TOXOUT (extensao local) — sanitizacao toxica do output em 3 niveis.

Conformidade:
- RailResult eh importado de agent_framework.guardrails_old.nemo.models (mesma estrutura).
- USE_MOCK_LLM env var respeitada (mesmo nome/default da lib).
- Multi-provider via TIM_LLM_PROVIDER (oci/openai/groq/...) para AOFERTA e
  TOXOUT atraves de agente_contas_tim.agent.infra.langchain.llm_factory.create_langchain_llm.
"""
from .input_size import verificar_tamanho_input
from .llm_rails import ausencia_oferta_proativa, compliance_anatel, out_of_scope, detectar_toxicidade
from .contestation_validation import validate_contestation_items
from .output_sanitization import (
    mascarar_pii_output,
    sanitizar_output,
    sanitizar_toxicidade_output,
)
from .pipeline import (
    RailDecision,
    apply_input_rails,
    apply_output_rails,
    _verbalizacao_prematura,
)


def verbalizacao_prematura(
    text: str,
    context: dict | None = None,
    callbacks: list | None = None,
):
    return _verbalizacao_prematura(
        text,
        context=context,
        callbacks=callbacks,
    )

__all__ = [
    "verificar_tamanho_input",
    "ausencia_oferta_proativa",
    "detectar_toxicidade",
    "compliance_anatel",
    "out_of_scope",
    "apply_input_rails",
    "apply_output_rails",
    "validate_contestation_items",
    "verbalizacao_prematura",
    "mascarar_pii_output",
    "sanitizar_output",
    "sanitizar_toxicidade_output",
    "RailDecision",
]
