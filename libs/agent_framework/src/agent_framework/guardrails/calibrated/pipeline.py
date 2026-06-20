"""Pipeline de guardrails do agente (Padrao 1 do guia da lib).

Encapsula os rails de input/output que aplicamos hoje:
- MSK no input (mascara PII antes do LLM).
- OOS no input (bloqueia mensagens fora de escopo).
- AOFERTA (oferta proativa nao solicitada) — extensao local.
- REVPREC (promessa operacional futura) — extensao local (prompt em prompts/revprec.py).

Sanitizacao de output (PII masking + toxicidade, sanitize-and-pass-through)
tambem existe em `output_sanitization.sanitizar_output`, com semantica
distinta (nao bloqueia, transforma o texto).

Quem chama recebe um RailDecision e age: se allowed=False, troca o texto da
resposta por fallback_text; se sanitized_text mudou, deve seguir o turno com
esse texto. O modulo eh puro de telemetria — quem invoca
(LangChainWorkflowAgent.run) e responsavel por emitir o span
'guardrail.<CODE>.blocked' no Langfuse usando a mixin de observabilidade
do agente.
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable

from ._compat import RailResult, span
from .input_size import verificar_tamanho_input
from .llm_client import GuardrailLLMClient
from .llm_rails import ausencia_oferta_proativa, compliance_anatel, out_of_scope, detectar_prompt_injection_jailbreak, detectar_rag_injection_context_poisoning, detectar_data_leakage_input, detectar_data_leakage_output, detectar_toxicidade, detectar_fallback
from .output_sanitization import mascarar_pii_output
from .rules.pinj_patterns import is_obvious_injection
from .rails.tox import ToxRail
import time

_tox_rail = ToxRail()

_client = GuardrailLLMClient()


logger = logging.getLogger(__name__)

# 2026-05-16
_FALLBACK_BY_CODE: dict[str, str] = {
    "INPUT_SIZE": (
        "Sua mensagem ficou muito longa pra eu processar de uma vez. "
        "Pode reformular de forma mais curta ou dividir em partes menores "
        "e me reenviar?"
    ),
    "AOFERTA": (
        "Posso te ajudar com mais alguma dúvida sobre sua conta ou fatura?"
    ),
    "REVPREC": (
        "No momento não consigo confirmar essa ação dessa forma. "
        "Vou continuar verificando as informações disponíveis."
    ),
    "CMP": (
        "Não consegui validar todas as informações necessárias neste momento. "
        "Vou seguir verificando os dados do atendimento."
    ),
    "OOS": (
        "Essa solicitação está fora do meu escopo de atendimento. "
        "Posso te ajudar com dúvidas sobre contas, consumo ou faturas da TIM."
    ),
    "DLEX_IN": (
        "Não consegui interpretar essa solicitação com segurança. "
        "Pode reformular sua mensagem de outra forma?"
    ),
    "PINJ": (
        "Não consegui processar essa solicitação da forma enviada. "
        "Pode reformular sua pergunta para continuarmos?"
    ),
    "RAGSEC": (
        "Não encontrei informações suficientes para responder isso com segurança. "
        "Pode detalhar melhor sua solicitação?"
    ),
    "DLEX_OUT": (
        "Prefiro reformular minha resposta para evitar informações incorretas. "
        "Pode me confirmar exatamente o que deseja consultar?"
    ),
    "TOX": (
        "Entendo que essa situação é frustrante. Vou te ajudar a verificar isso."
    ),
    "INTENCAO_CANCELAR": (
        "Deixa eu confirmar o que você gostaria de fazer: você quer entender "
        "o que é essa cobrança ou prefere cancelar o serviço?"
    ),
    "CORRESPONDENCIA_ITEM": (
        "Preciso confirmar um detalhe antes de prosseguirmos. Pode me confirmar "
        "qual serviço você deseja cancelar e o valor que esperava?"
    ),
    "ALCADA": (
        "Este ajuste precisa ser analisado por um especialista TIM. "
        "Vou encaminhar seu atendimento para continuar com um especialista "
        "que poderá te ajudar melhor nesse caso."
    ),
    "ACTION_CONFIRMATION_RETRY": (
        "Antes de prosseguirmos, preciso confirmar: você gostaria mesmo de "
        "realizar essa ação?"
    ),
}

#2026-05-19
def _run_rail(
        timings_ms: dict[str, float],
        code: str,
        fn,
        *args,
        **kwargs,
):
    started = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed = round((time.perf_counter() - started) * 1000, 3)
    timings_ms[code] = elapsed
    return result


# (code, fn, kwargs) -> RailResult. O runner e responsavel por: cronometrar,
# popular `timings_ms`, abrir spans Langfuse e injetar `callbacks` nas rails
# LLM que aceitam. O default abaixo replica o `_run_rail` original (sem
# tracing/callbacks) — usado quando o pipeline e invocado fora do agent (ex.:
# testes, scripts).
RailRunner = Callable[[str, Callable[..., "RailResult"], dict], "RailResult"]


def _default_rail_runner(
    timings_ms: dict[str, float],
) -> RailRunner:
    def runner(code: str, fn, kwargs: dict):
        return _run_rail(timings_ms, code, fn, **kwargs)
    return runner

_MOCK_WARNED = False


def _maybe_warn_mock_mode() -> None:
    """Loga UMA vez por processo se os rails LLM estao em modo mock.

    Em producao, USE_MOCK_LLM=false desliga o aviso. Em dev/test fica visivel
    para evitar que alguem confunda heuristica de string-match com LLM real.
    """
    global _MOCK_WARNED
    if _MOCK_WARNED:
        return
    if os.getenv("USE_MOCK_LLM", "true").lower() == "true":
        logger.warning(
            "guardrails rodando em modo MOCK (USE_MOCK_LLM=true). "
            "Os rails LLM (AOFERTA, REVPREC) usam heuristicas "
            "deterministicas; em producao defina USE_MOCK_LLM=false."
        )
    _MOCK_WARNED = True


@dataclass
class RailDecision:
    allowed: bool
    code: str | None = None
    reason: str = ""
    fallback_text: str | None = None
    sanitized_text: str | None = None
    results: list[RailResult] = field(default_factory=list)
    timings_ms: dict[str, float] = field(default_factory=dict)
    total_ms: float = 0.0
    # Distingue hard-block (substitui resposta) de soft-alert (apenas loga).
    # False = default = hard-block: substituir result["content"] + patchar histórico.
    # True = soft-alert: logar violação, não alterar a resposta ao cliente.
    is_soft_alert: bool = False
    # Flag corretiva para re-invocar o agente principal com constraint.
    # None = rail não suporta regeneração (usa apenas fallback estático).
    regen_flag: str | None = None

def _verbalizacao_prematura(
    text: str,
    context: dict = None,
    *,
    callbacks: list | None = None,
) -> RailResult:
    """Rail REVPREC local: bloqueia promessa operacional futura.

    Roteia via GuardrailLLMClient (mesmo client de AOFERTA/TOXOUT), usando o
    prompt local em prompts/revprec.py. Avalia apenas o texto final do agente,
    sem contexto ou tool_calls. Em modo mock (USE_MOCK_LLM=true), recai na
    heuristica deterministica de _mock_classify("REVPREC", ...).
    """
    with span("rail.REVPREC", mechanism="llm_rail"):
        out = _client.classify(
            "REVPREC",
            {"text": text, "context": context or {}},
            callbacks=callbacks,
        )
        return RailResult(
            allowed=bool(out.get("allowed", True)),
            reason=out.get("reason", ""),
            sanitized_text=text,
            code="REVPREC",
            mechanism="llm_rail",
            data=out,
        )


def apply_input_rails(
    text: str,
    *,
    rail_runner: RailRunner | None = None,
) -> RailDecision:
    """Aplica INPUT_SIZE + MSK + OOS no input. Curto-circuita ao primeiro bloqueio.

    `rail_runner` opcional permite ao caller (LangChainWorkflowAgent) abrir
    spans Langfuse por rail e injetar callbacks Langfuse nos rails LLM. Quando
    omitido, usa o runner default que apenas cronometra (caso de testes e
    scripts).
    """
    _maybe_warn_mock_mode()
    results: list[RailResult] = []

    timings_ms = {}
    pipeline_started = time.perf_counter()
    runner = rail_runner or _default_rail_runner(timings_ms)

    #desativação para integração futura
    return RailDecision(
        allowed=True,
        sanitized_text=text,
        results=results,
        timings_ms=timings_ms,
        total_ms=round(
            (time.perf_counter() - pipeline_started) * 1000,
            3
        ),
    )

    # AT-09: first-pass determinístico para PINJ óbvio — evita chamada LLM
    # para padrões de injection inequívocos (role override, pseudo-tags, etc.)
    if is_obvious_injection(text):
        timings_ms["PINJ"] = round((time.perf_counter() - pipeline_started) * 1000, 3)
        return RailDecision(
            allowed=False,
            code="PINJ",
            reason="regex_match: padrão de injection óbvio detectado sem LLM",
            fallback_text=_FALLBACK_BY_CODE["PINJ"],
            results=results,
            timings_ms=timings_ms,
            total_ms=timings_ms["PINJ"],
        )

    # PINJ (LLM) e INPUT_SIZE executados em paralelo (AT-13): INPUT_SIZE é
    # determinístico e pode terminar antes. PINJ tem precedência de bloqueio.
    with ThreadPoolExecutor(max_workers=2) as executor:
        pinj_future = executor.submit(
            runner,
            "PINJ",
            detectar_prompt_injection_jailbreak,
            {"text": text, "context": {}},
        )
        size_future = executor.submit(
            runner,
            "INPUT_SIZE",
            verificar_tamanho_input,
            {"text": text, "context": {}},
        )
        pinj = pinj_future.result()
        size = size_future.result()

    results.append(pinj)
    if not pinj.allowed:
        try:
            fallback = runner(
                "FALLBACK_PINJ",
                detectar_fallback,
                {
                    "text": text,
                    "context": {},
                    "guardrail_code": "PINJ",
                    "guardrail_reason": pinj.reason,
                },
            ).reason
        except Exception:
            fallback = _FALLBACK_BY_CODE["PINJ"]

        return RailDecision(
            allowed=False,
            code="PINJ",
            reason=pinj.reason,
            fallback_text=fallback,
            results=results,
            timings_ms=timings_ms,
            total_ms=round(
                (time.perf_counter() - pipeline_started) * 1000,
                3
            ),
        )

    # TOX: reativado em AT-05 com mecanismo de baixa latência.
    # Novo mecanismo: blocklist determinística (is_obvious_toxic) + LLM leve (ToxRail).
    # Executa em paralelo com OOS/AOFERTA via pipeline — não adiciona latência sequencial.
    # Ativado via env var GUARDRAIL_TOX_ENABLED=true (desativado por default).
    if os.getenv("GUARDRAIL_TOX_ENABLED", "false").lower() == "true":
        from .contracts import GuardRailContext as _GRCtx
        _tox_ctx = _GRCtx(session_id="pipeline", user_text=text)
        tox_started = time.perf_counter()
        tox_decision = _tox_rail.evaluate(_tox_ctx)
        timings_ms["TOX"] = round((time.perf_counter() - tox_started) * 1000, 3)

        if not tox_decision.allowed:
            return RailDecision(
                allowed=False,
                code="TOX",
                reason=tox_decision.reason,
                fallback_text=tox_decision.fallback_text or _FALLBACK_BY_CODE["TOX"],
                sanitized_text=text,
                results=results,
                timings_ms=timings_ms,
                total_ms=round(
                    (time.perf_counter() - pipeline_started) * 1000,
                    3,
                ),
            )

    results.append(size)
    if not size.allowed:
        try:
            fallback = runner(
                "FALLBACK_INPUT_SIZE",
                detectar_fallback,
                {
                    "text": text,
                    "context": {},
                    "guardrail_code": "INPUT_SIZE",
                    "guardrail_reason": size.reason,
                },
            ).reason
        except Exception:
            fallback = _FALLBACK_BY_CODE["INPUT_SIZE"]

        return RailDecision(
            allowed=False,
            code="INPUT_SIZE",
            reason=size.reason,
            fallback_text=fallback,
            sanitized_text=text,
            results=results,
            timings_ms=timings_ms,
            total_ms=round(
                (time.perf_counter() - pipeline_started) * 1000,
                3
            ),
        )

    msk = runner(
        "MSK",
        mascarar_pii_output,
        {"text": text, "context": {}},
    )

    results.append(msk)
    sanitized_text = msk.sanitized_text or text

    # [RAIL] migrado para guardrails/rails/dlex_in.py — ativação via GuardRailConfig.dlex_in_enabled

    return RailDecision(
        allowed=True,
        sanitized_text=sanitized_text,
        results=results,
        timings_ms=timings_ms,
        total_ms=round(
            (time.perf_counter() - pipeline_started) * 1000,
            3
        ),
    )

# 2026-05-16
def apply_output_rails(
    text: str,
    user_text: str,
    tool_calls: list[dict[str, Any]] | None,
    context: dict[str, Any] | None = None,
    *,
    rail_runner: RailRunner | None = None,
) -> RailDecision:
    """Aplica OOS + AOFERTA na resposta do agente.

    Curto-circuita no primeiro bloqueio para economizar 1 chamada LLM.
    AOFERTA julga apenas a fala do agente, sem depender do historico.

    `rail_runner` opcional permite ao caller abrir spans Langfuse por rail e
    injetar callbacks nas rails LLM.

    Early-exit e invariante ``tool_calls``
    --------------------------------------
    Quando ``tool_calls`` é não-nulo (lista de uma ou mais tool_calls), esta
    função retorna imediatamente com ``allowed=True, reason="skipped_due_to_tool_calls"``
    sem executar OOS nem AOFERTA.

    **Invariante**: quando ``tool_calls`` está presente, o ``content`` do
    AIMessage contém **apenas** ``pre_message`` fixos — textos determinísticos
    gerados pelo agente para avisar o cliente que uma ação está prestes a ser
    executada (ex.: "Perfeito! Aguarde um instante."). Esses textos não contêm
    informação derivada de input do usuário e não são candidatos a OOS, AOFERTA
    ou REVPREC. Por isso a verificação de guardrail é desnecessária e seria
    apenas latência.

    **Responsabilidade do caller**: quem invoca ``apply_output_rails`` deve
    garantir essa invariante antes de popular ``tool_calls``. Em produção,
    ``LangChainWorkflowAgent.run`` satisfaz a invariante porque ``pre_message``
    é interpolado a partir de templates fixos registrados no fluxo, nunca a
    partir do texto do usuário.

    Consequência de auditoria: o texto passado via ``text`` quando
    ``tool_calls`` não é nulo **não é verificado por guardrail**. O logger.debug
    abaixo registra o skip com o tamanho do texto para rastreabilidade.
    """
    _maybe_warn_mock_mode()
    results: list[RailResult] = []
    timings_ms: dict[str, float] = {}
    pipeline_started = time.perf_counter()

    #desativação para integração futura
    return RailDecision(
            allowed=True,
            reason="skipped_due_integration",
            sanitized_text=text,
            results=results,
            timings_ms=timings_ms,
            total_ms=round(
                (time.perf_counter() - pipeline_started) * 1000,
                3,
            ),
        )
    
    # INVARIANTE: tool_calls presente → content = pre_message fixo (não requer guardrail)
    if tool_calls:
        logger.debug(
            "apply_output_rails.skipped_due_to_tool_calls "
            "text_len=%d tool_calls_count=%d",
            len(text),
            len(tool_calls),
        )
        return RailDecision(
            allowed=True,
            reason="skipped_due_to_tool_calls",
            sanitized_text=text,
            results=results,
            timings_ms=timings_ms,
            total_ms=round(
                (time.perf_counter() - pipeline_started) * 1000,
                3,
            ),
        )
    # OOS e AOFERTA executados em paralelo (AT-12): cada um = 1 chamada LLM.
    # Submetemos ambos ao mesmo tempo e aguardamos os dois resultados antes de
    # tomar decisão. OOS tem precedência sobre AOFERTA se ambos bloquearem.
    runner = rail_runner or _default_rail_runner(timings_ms)

    with ThreadPoolExecutor(max_workers=2) as executor:
        oos_future = executor.submit(
            runner,
            "OOS",
            out_of_scope,
            {"text": text, "context": context or {}},
        )
        aof_future = executor.submit(
            runner,
            "AOFERTA",
            ausencia_oferta_proativa,
            {"text": text, "context": context or {}},
        )
        oos = oos_future.result()
        aof = aof_future.result()

    results.append(oos)
    results.append(aof)

    # ESTRATÉGIA DE REATIVAÇÃO DA REESCRITA LLM (camada 2) — FC-07:
    # Camada 3 (regeneração via _REGEN_FLAG_BY_CODE) tem precedência para:
    #   AOFERTA, OOS, INTENCAO_CANCELAR, CORRESPONDENCIA_ITEM, TOX, REVPREC, RAGSEC, ALCADA.
    # Camada 2 (reescrita LLM externa via detectar_fallback) é fallback da camada 3,
    #   ou path principal para rails sem regen_flag (INPUT_SIZE, PINJ).
    # Camada 1 (texto estático) é usado somente quando camada 2 está off ou falha.
    # Para reativar camada 2: descomentar o bloco detectar_fallback abaixo e garantir
    #   que todos os rails hard-block tenham entry em _REWRITE_INSTRUCTIONS_BY_CODE.

    if not oos.allowed:
        # Fallback gerado por LLM desativado: no momento so importa a deteccao.
        # Mantido comentado para reativar quando a reescrita voltar a ser usada.
        # try:
        #     fallback = runner(
        #         "FALLBACK_OOS",
        #         detectar_fallback,
        #         {
        #             "text": text,
        #             "context": context or {},
        #             "guardrail_code": "OOS",
        #             "guardrail_reason": oos.reason,
        #         },
        #     ).reason
        # except Exception:
        #     fallback = _FALLBACK_BY_CODE["OOS"]
        fallback = _FALLBACK_BY_CODE["OOS"]

        return RailDecision(
            allowed=False,
            code="OOS",
            reason=oos.reason,
            fallback_text=fallback,
            sanitized_text=text,
            results=results,
            timings_ms=timings_ms,
            total_ms=round(
                (time.perf_counter() - pipeline_started) * 1000,
                3
            ),
        )

    if not aof.allowed:
        # Fallback gerado por LLM desativado: no momento so importa a deteccao.
        # Mantido comentado para reativar quando a reescrita voltar a ser usada.
        # try:
        #     fallback = runner(
        #         "FALLBACK_AOFERTA",
        #         detectar_fallback,
        #         {
        #             "text": text,
        #             "context": context or {},
        #             "guardrail_code": "AOFERTA",
        #             "guardrail_reason": aof.reason,
        #         },
        #     ).reason
        # except Exception:
        #     fallback = _FALLBACK_BY_CODE["AOFERTA"]
        fallback = _FALLBACK_BY_CODE["AOFERTA"]

        return RailDecision(
            allowed=False,
            code="AOFERTA",
            reason=aof.reason,
            fallback_text=fallback,
            results=results,
            timings_ms=timings_ms,
            total_ms=round(
                (time.perf_counter() - pipeline_started) * 1000,
                3
            ),
        )

    # [RAIL] migrado para guardrails/rails/revprec.py — ativação via GuardRailConfig.revprec_enabled

    # [RAIL] migrado para guardrails/rails/ragsec.py — ativação via GuardRailConfig.ragsec_enabled

    # [RAIL] migrado para guardrails/rails/dlex_out.py — ativação via GuardRailConfig.dlex_out_enabled

    # CMP (compliance_anatel) é "sanitize-and-pass-through": roda no
    # `_finalize_run` da loop junto com MSK/TOXOUT pra que o span
    # `guardrail.CMP.applied` seja registrado antes do
    # `run_observation.update(output=...)`. Não entra aqui porque os rails
    # acima são bloqueantes e este é deterministicamente recuperável.

    return RailDecision(allowed=True, results=results,
                        timings_ms=timings_ms,
                        total_ms=round(
                            (time.perf_counter() - pipeline_started) * 1000,
                            3
                            ),
                        )

def replace_last_ai_message(history: list[Any], new_content: str) -> bool:
    """Substitui o `content` da ultima AIMessage do historico do agente.

    Necessario quando um rail de saida bloqueia: o handler troca o texto
    devolvido ao cliente, mas a AIMessage original (com a frase ofensiva)
    ainda esta no historico do agente — no proximo turno, o LLM ve aquela
    frase e pode reincidir. Patcheamos in-place para que o historico
    passe a refletir o fallback.

    Retorna True se conseguiu trocar; False quando nao acha AIMessage.
    """
    for msg in reversed(history):
        cls = type(msg).__name__
        if cls != "AIMessage":
            continue
        try:
            msg.content = new_content
        except Exception:
            return False
        return True
    return False
