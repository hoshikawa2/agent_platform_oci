"""Rails de sanitizacao do output do agente.

Dois rails sanitize-and-pass-through (nao bloqueiam, transformam o texto):

- `mascarar_pii_output(text) -> RailResult` (code=MSK)
  PII masking via regex local (CPF, cartao, senha) com fallback opcional para
  `agent_framework.guardrails_old.nemo.deterministic_rails.mask_pii` quando a lib
  conseguir importar.

- `sanitizar_toxicidade_output(text) -> RailResult` (code=TOXOUT)
  Toxicidade do output em 3 niveis:
   - Nivel 1: deteccao deterministica via regex (sem custo LLM). Quando
     encontra trecho toxico, NAO devolve direto: escala para o nivel 2 para
     evitar fragmentos sem coesao (ex.: "voce eh seu" apos remocao de
     palavrao). O texto pre-limpo so eh usado como fallback do fallback.
   - Nivel 2: reescrita via LLM atraves do GuardrailLLMClient (TOXOUT).
   - Nivel 3: mensagem canonica fixa do dominio.

Ambos retornam `RailResult.allowed=True`; o caller substitui o texto por
`sanitized_text` quando `sanitized_text != text`. A funcao agregadora
`sanitizar_output` mantem retrocompat e roda os dois em sequencia.
"""
from __future__ import annotations

import logging
import re

from ._compat import RailResult, span
from .llm_client import GuardrailLLMClient


logger = logging.getLogger(__name__)


_TOXIC_PATTERNS = (
    r"\b(idiota|imbecil|burro|estúpido|inútil|maldito|miserável|incompetente)\b",
    r"\b(idiots?|stupid|useless|moron)\b",
)


_PII_RULES: tuple[tuple[str, str], ...] = (
    # CPF formatado (xxx.xxx.xxx-xx).
    (r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", "[CPF_MASCARADO]"),
    # Cartao com 16 digitos contiguos.
    (r"\b\d{16}\b", "[CARTAO_MASCARADO]"),
)
# Senha em padrao "senha: xxx" / "senha=xxx" — usa grupo capturado como prefixo.
_PII_PASSWORD_PATTERN = r"(?i)(senha\s*[:=]?\s*)\S+"
_PII_PASSWORD_REPL = r"\1[SENHA_MASCARADA]"


_TOXOUT_CANONICAL_MESSAGE = (
    "Não consegui formular uma resposta adequada, posso ajudar de outra forma?"
)


_client = GuardrailLLMClient()


def _deterministic_sanitize(text: str) -> tuple[str, bool]:
    """Nivel 1: remove padroes toxicos comuns via regex.

    Retorna (texto_sanitizado, perdeu_sentido). Considera que perdeu sentido
    se o texto resultante ficou com menos de 50% do tamanho original.
    """
    sanitized = text
    for pattern in _TOXIC_PATTERNS:
        sanitized = re.sub(pattern, "", sanitized, flags=re.IGNORECASE)
    sanitized = " ".join(sanitized.split())
    lost_meaning = len(sanitized) < len(text) * 0.5
    return sanitized, lost_meaning


def _regex_is_clean(text: str) -> bool:
    """Verifica via regex local se o texto nao contem padroes toxicos conhecidos."""
    for pattern in _TOXIC_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return False
    return True


def _mask_pii_local(text: str) -> str:
    """Implementacao local equivalente a `mask_pii` da lib.

    Replica os mesmos padroes de `agent_framework.guardrails_old.nemo
    .deterministic_rails.mask_pii` (CPF formatado, cartao de 16 digitos
    e padrao "senha: xxx"). Mantemos local porque a lib hoje fica presa
    atras de um import eager de `nemoguardrails`, que conflita com as
    versoes de langchain/fastapi que a propria `agent_framework` exige.
    """
    masked = text
    for pattern, replacement in _PII_RULES:
        masked = re.sub(pattern, replacement, masked)
    masked = re.sub(_PII_PASSWORD_PATTERN, _PII_PASSWORD_REPL, masked)
    return masked


def _mask_pii(text: str) -> str:
    """Tenta a `mask_pii` da lib; em qualquer falha, cai na versao local."""
    try:
        from agent_framework.guardrails_old.nemo.deterministic_rails import (
            mask_pii,
        )

        return mask_pii(text).sanitized_text or text
    except Exception:
        logger.debug(
            "guardrails.mask_pii_lib_indisponivel_usando_regex_local",
            exc_info=True,
        )
        return _mask_pii_local(text)


def _detectar_toxicidade_safe(text: str):
    """Usa o detectar_toxicidade local (GuardrailLLMClient).

    Antes lazy-importava de agent_framework.guardrails_old.nemo, cujo cliente
    OpenAI aponta para OPENAI_BASE_URL=localhost:8051 e causa
    APIConnectionError + retries longos quando o proxy nao esta de pe.
    Mesma migracao ja feita para out_of_scope.
    """
    from .llm_rails import detectar_toxicidade

    return detectar_toxicidade(text)


def _is_clean(text: str) -> bool:
    """Confirma que o texto reescrito nao tem mais toxicidade.

    Tenta `detectar_toxicidade` da lib; se a lib nao estiver disponivel
    (ex.: nemoguardrails ausente em dev), cai num check de regex local.
    """
    try:
        return bool(_detectar_toxicidade_safe(text).allowed)
    except Exception:
        logger.debug("guardrails.tox_check_unavailable_using_regex", exc_info=True)
        return _regex_is_clean(text)


def _sanitize_toxic(
    text: str,
    *,
    callbacks: list | None = None,
) -> tuple[str, str]:
    """Pipeline 3-niveis de sanitizacao toxica.

    Retorna (texto_final, nivel) onde nivel ∈ {"deterministic", "llm_rewrite",
    "canonical", "noop"}. "noop" indica que nada toxico foi achado e o texto
    voltou inalterado.

    `callbacks` (opcional) e repassado para `_client.classify` quando o nivel
    2 (LLM rewrite) dispara, para que o ChatLLM da reescrita apareca como
    span no Langfuse.
    """
    with span("rail.TOXOUT.deterministic", mechanism="regex"):
        pre_cleaned, lost_meaning = _deterministic_sanitize(text)
        if pre_cleaned == text:
            return text, "noop"
        logger.info(
            "guardrails.toxic_sanitized_deterministically lost_meaning=%s",
            lost_meaning,
        )

    with span("rail.TOXOUT.llm_rewrite", mechanism="llm_supervisor"):
        try:
            out = _client.classify("TOXOUT", {"text": text}, callbacks=callbacks)
            rewritten = (out.get("text") or "").strip()
            logger.warning(
                "guardrails.toxout_llm_raw use_mock=%s rewritten_len=%s rewritten=%r is_clean=%s",
                _client.use_mock,
                len(rewritten),
                rewritten[:200],
                _is_clean(rewritten) if rewritten else False,
            )
            #rewritten = (out.get("text") or "").strip()
            if rewritten and _is_clean(rewritten):
                logger.info("guardrails.toxic_rewritten_by_llm")
                return rewritten, "llm_rewrite"
        except Exception:
            logger.warning(
                "guardrails.sanitize_toxic_llm_failed", exc_info=True,
            )

    if not lost_meaning:
        logger.warning(
            "guardrails.toxic_sanitized_deterministically_fallback",
        )
        return pre_cleaned, "deterministic"

    with span("rail.TOXOUT.canonical", mechanism="python"):
        logger.warning("guardrails.toxic_fallback_canonical")
        return _TOXOUT_CANONICAL_MESSAGE, "canonical"


def mascarar_pii_output(text: str, context: dict = None) -> RailResult:
    """Rail de PII masking no output (code=MSK).

    Sempre retorna allowed=True. Quando algum padrao foi encontrado,
    `sanitized_text != text` e o caller deve emitir um span
    `guardrail.MSK.applied` antes de substituir.
    """
    with span("rail.MSK", mechanism="regex"):
        masked = _mask_pii(text)
        changed = masked != text
        if changed:
            logger.warning(
                "guardrails.output_pii_mascarado original_len=%s sanitized_len=%s",
                len(text),
                len(masked),
            )
        return RailResult(
            allowed=True,
            reason="PII mascarada" if changed else "Nenhuma PII detectada",
            sanitized_text=masked,
            code="MSK",
            mechanism="regex",
            data={
                "label": "SANITIZED" if changed else "OK",
                "original_len": len(text),
                "sanitized_len": len(masked),
            },
        )


def sanitizar_toxicidade_output(
    text: str,
    *,
    callbacks: list | None = None,
) -> RailResult:
    """Rail de sanitizacao toxica no output (code=TOXOUT).

    Sempre retorna allowed=True. Quando o texto foi reescrito,
    `sanitized_text != text` e o caller deve emitir um span
    `guardrail.TOXOUT.applied` antes de substituir.

    `callbacks` (opcional) e repassado para o LLM da reescrita; sem ele,
    a chamada do LLM nao aparece no Langfuse.
    """
    with span("rail.TOXOUT", mechanism="llm_supervisor"):
        try:
            tox = _detectar_toxicidade_safe(text)
            tox_allowed = bool(tox.allowed)
            tox_reason = tox.reason
        except Exception:
            logger.warning(
                "guardrails.toxicidade_check_failed_using_safe_fallback",
                exc_info=True,
            )
            tox_allowed = _regex_is_clean(text)
            tox_reason = "lib indisponivel; usando regex local"

        if tox_allowed:
            return RailResult(
                allowed=True,
                reason="output limpo",
                sanitized_text=text,
                code="TOXOUT",
                mechanism="llm_supervisor",
                data={"label": "OK", "level": "noop"},
            )

        logger.warning(
            "guardrails.output_toxicidade_detectada reason=%s", tox_reason,
        )
        cleaned, level = _sanitize_toxic(text, callbacks=callbacks)

        if cleaned != text:
            logger.warning(
                "guardrails.output_sanitizado code=TOXOUT level=%s "
                "original=%r sanitizado=%r",
                level,
                text[:200],
                cleaned[:200],
            )

        return RailResult(
            allowed=True,
            reason="output sanitizado",
            sanitized_text=cleaned,
            code="TOXOUT",
            mechanism="llm_supervisor",
            data={
                "label": "SANITIZED" if cleaned != text else "OK",
                "level": level,
                "original_len": len(text),
                "sanitized_len": len(cleaned),
            },
        )


def sanitizar_output(
    text: str,
    *,
    callbacks: list | None = None,
) -> RailResult:
    """Wrapper retrocompativel: aplica MSK + TOXOUT em sequencia.

    Mantido para callers que nao se importam com spans granulares no Langfuse.
    Para emissao correta de spans `guardrail.MSK.applied` e
    `guardrail.TOXOUT.applied`, prefira chamar `mascarar_pii_output` e
    `sanitizar_toxicidade_output` diretamente do call site que tem acesso
    ao mixin de observabilidade do agente.
    """
    pii = mascarar_pii_output(text)
    tox = sanitizar_toxicidade_output(pii.sanitized_text or text, callbacks=callbacks)
    return tox
