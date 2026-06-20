from __future__ import annotations

import re

from ._compat import RailResult, span
from .llm_client import GuardrailLLMClient


_client = GuardrailLLMClient()

def detectar_toxicidade(text:str, context: dict = None, *, callbacks: list | None = None)->RailResult:
    with span("rail.TOX", mechanism="llm_rail"):
        out=_client.classify("TOX", {"text":text}, callbacks=callbacks); return RailResult(out["allowed"],out.get("reason",""),text,"TOX","llm_rail",out)

def ausencia_oferta_proativa(text: str, context: dict = None, *, callbacks: list | None = None) -> RailResult:
    """Supervisor LLM: bloqueia oferta proativa nao solicitada.

    Julga a fala mais recente do agente com referencia ao historico da
    conversa (quando o pipeline o fornece via `context`), para que o
    auditor consiga aplicar as regras 3a/3b do prompt — pedido de
    permissao para acao sobre itens que sao o assunto da conversa nao
    e proativa, mesmo quando o cliente nao repete os nomes na ultima
    fala. Padroes de linguagem proativa ("quer aproveitar e...",
    "ja que esta...") seguem caracterizando oferta indevida.

    Args:
        text: ultima fala do agente a ser auditada.
        context: dict com `conversation_history` (formatado por
            `format_context_block` em `llm_client.classify`).

    Returns:
        RailResult com code="AOFERTA", mechanism="llm_supervisor".
        allowed=False quando o agente propoe acao nao solicitada.
    """
    with span("supervisor.AOFERTA", mechanism="llm_supervisor"):
        out = _client.classify(
            "AOFERTA",
            {"text": text, "context": context or {}},
            callbacks=callbacks,
        )
        return RailResult(
            allowed=bool(out.get("allowed", False)),
            reason=out.get("reason", ""),
            sanitized_text=text,
            code="AOFERTA",
            mechanism="llm_supervisor",
            data=out,
        )


_DIGIT_WORDS_RE = (
    r"(?:zero|um|dois|tr[êe]s|quatro|cinco|seis|sete|oito|nove)"
)
# Token vocalizado: palavra de dígito ou letra única (a-z).
_SPOKEN_TOKEN_RE = rf"(?:{_DIGIT_WORDS_RE}|[a-z])"
# 6+ tokens vocalizados separados por espaço (cobre PRT-XXXX vocalizado).
_SPOKEN_PROTOCOL_RE = (
    rf"(?:{_SPOKEN_TOKEN_RE}\s+){{5,}}{_SPOKEN_TOKEN_RE}\b"
)
_PROTOCOL_PATTERN = re.compile(
    r"(?i)\bprotocolo\b"
    r"[\s\S]{0,40}?"
    r"(?:"
        r"\d{6,}"                   # formato legado: 6+ dígitos literais
        r"|"
        r"PRT-[A-Z0-9]{6,}"         # formato bruto da TIM (caso o LLM não vocalize)
        r"|"
        rf"{_SPOKEN_PROTOCOL_RE}"   # formato vocalizado (palavras + letras)
    r")"
)


def compliance_anatel(text: str, context: dict) -> RailResult:
    """Rail CMP: garante que respostas de ajuste contenham número de protocolo.

    Aplica apenas quando o fluxo exige protocolo (tipo_fluxo='ajuste' ou
    requer_protocolo=True no context). Se não aplicável, passa direto.
    Aceita 3 formatos após "protocolo": dígitos literais (6+), `PRT-XXXX`
    bruto, ou 6+ tokens vocalizados (palavras de dígito ou letras únicas).

    Quando bloqueia, devolve em `data["expected_protocols"]` os números
    crus que estavam pendentes no context — o caller pode usar para
    aplicar fallback determinístico (concatenar a frase de protocolo).
    """
    with span("rail.CMP", mechanism="regex"):
        requer = (
            context.get("tipo_fluxo") == "ajuste"
            or context.get("requer_protocolo") is True
        )
        if not requer:
            return RailResult(
                allowed=True,
                reason="Compliance Anatel não aplicável",
                sanitized_text=text,
                code="CMP",
                mechanism="regex",
            )
        expected = list(context.get("expected_protocols") or [])
        has_protocol = bool(_PROTOCOL_PATTERN.search(text))
        if not has_protocol:
            return RailResult(
                allowed=False,
                reason="Resposta de ajuste sem número de protocolo",
                sanitized_text=text,
                code="CMP",
                mechanism="regex",
                data={"expected_protocols": expected},
            )
        return RailResult(
            allowed=True,
            reason="Resposta contém protocolo obrigatório",
            sanitized_text=text,
            code="CMP",
            mechanism="regex",
        )


def out_of_scope(text: str, context: dict = None, *, callbacks: list | None = None) -> RailResult:
    """Rail OOS: bloqueia mensagens fora do dominio Telecom (contas/faturas TIM).

    Roteia via GuardrailLLMClient (mesmo client de AOFERTA/REVPREC/TOXOUT) para
    que o rail respeite TIM_LLM_PROVIDER (Groq/OCI/Azure/...) e USE_MOCK_LLM.
    Antes delegava para `agent_framework.guardrails.nemo.llm_rails.detectar_out_of_scope`,
    que tem cliente OpenAI proprio com defaults `OPENAI_BASE_URL=localhost:8051`
    — incompativel com o setup do projeto e causa de APIConnectionError quando
    USE_MOCK_LLM=false.
    """
    with span("rail.OOS", mechanism="llm_supervisor"):
        out = _client.classify(
            "OOS",
            {"text": text, "context": context or {}},
            callbacks=callbacks,
        )
        allowed = bool(out.get("allowed", True))
        return RailResult(
            allowed=allowed,
            reason=out.get("reason", ""),
            sanitized_text=text,
            code="OOS",
            mechanism="llm_supervisor",
            data=out,
        )


# =========================
# FILTROS ADICIONADOS DE SEGURANCA
# =========================

def detectar_prompt_injection_jailbreak(text:str, context:dict, *, callbacks: list | None = None)->RailResult:
    with span("rail.PINJ", mechanism="llm_rail"):
        out=_client.classify("PINJ", {"text":text,"context":context}, callbacks=callbacks);
        return RailResult(out["allowed"],out.get("reason",""),text,"PINJ","llm_rail",out)

def detectar_rag_injection_context_poisoning(text:str, context:dict, *, callbacks: list | None = None)->RailResult:
    with span("rail.RAGSEC", mechanism="llm_rail"):
        out=_client.classify("RAGSEC", {"text":text,"context":context}, callbacks=callbacks);
        return RailResult(out["allowed"],out.get("reason",""),text,"RAGSEC","llm_rail",out)

def detectar_data_leakage_input(text:str, context:dict, *, callbacks: list | None = None)->RailResult:
    with span("rail.DLEX_IN", mechanism="llm_rail"):
        out=_client.classify("DLEX_IN", {"text":text,"context":context}, callbacks=callbacks);
        return RailResult(out["allowed"],out.get("reason",""),text,"DLEX_IN","llm_rail",out)

def detectar_data_leakage_output(text:str, context:dict, *, callbacks: list | None = None)->RailResult:
    with span("rail.DLEX_OUT", mechanism="llm_rail"):
        out=_client.classify("DLEX_OUT", {"text":text,"context":context}, callbacks=callbacks);
        return RailResult(out["allowed"],out.get("reason",""),text,"DLEX_OUT","llm_rail",out)

def detectar_fallback(
    text: str,
    context: dict = None,
    *,
    guardrail_code: str | None = None,
    guardrail_reason: str | None = None,
    callbacks: list | None = None,
) -> RailResult:
    """Reescreve o texto bloqueado por um rail.

    `guardrail_code` e `guardrail_reason` vêm do `RailResult` do rail que
    disparou — o prompt usa essa info para escolher a instrução de reescrita
    específica (AOFERTA remove oferta proativa, REVPREC remove promessa de
    ação, OOS redireciona ao escopo etc.). Sem esses kwargs o prompt cai
    numa instrução genérica.
    """
    with span("fallback", mechanism="llm_rail"):
        out = _client.classify(
            "FALLBACK",
            {
                "text": text,
                "context": context,
                "guardrail_code": guardrail_code,
                "guardrail_reason": guardrail_reason,
            },
            callbacks=callbacks,
        )
        return RailResult(
            out["allowed"],
            out.get("reason", ""),
            text,
            "FALLBACK",
            "llm_rail",
            out,
        )
