from __future__ import annotations

import json
import os
import re
from typing import Any

from .prompts.ausencia_oferta_proativa import build_aoferta_prompt
from .prompts._context import format_context_block
from .prompts.out_of_scope import build_oos_prompt
from .prompts.revprec import build_revprec_prompt
from .prompts.toxicidade_output import build_toxout_rewrite_prompt
from .prompts.tox import build_tox_prompt

# Segurança
from .prompts.dlex_in import build_dlex_in_prompt
from .prompts.dlex_out import build_dlex_out_prompt
from .prompts.pinj import build_pinj_prompt
from .prompts.ragsec import build_ragsec_prompt
from .prompts.fallback import build_fallback_prompt

_AOFERTA_TRIGGERS = (
    "quer aproveitar",
    "que tal tambem",
    "que tal também",
    "posso ja",
    "posso já",
    "ja que esta",
    "já que está",
    "aproveita e",
    "aproveite e",
    "tambem cancelar",
    "também cancelar",
)


_REVPREC_MARKERS = (
    "vou retirar o valor",
    "vou retirar a cobranca",
    "vou retirar a cobrança",
    "vou cancelar o servico",
    "vou cancelar o serviço",
    "vou cancelar a cobranca",
    "vou cancelar a cobrança",
    "vou devolver o valor",
    "vou retornar o valor",
    "sera devolvido para voce",
    "será devolvido para você",
)


_TOXOUT_MOCK_PATTERNS = (
    r"\b(idiota|imbecil|burro|estúpido|inútil|maldito|miserável|incompetente)\b",
    r"\b(idiots?|stupid|useless|moron)\b",
)


_OOS_MOCK_TRIGGERS = (
    "política",
    "religião",
    "presidente",
    "concorrente",
    "vivo",
)


class GuardrailLLMClient:
    """Roteador de prompts para os guardrails de supervisao TIM.

    Mesma forma do LLMClient da lib (agent_framework.guardrails.nemo.llm_client),
    mas roteia somente a task propria (AOFERTA) e usa o LLM do projeto
    (langchain) via create_langchain_llm, herdando suporte a OCI, OpenAI,
    Groq, Azure etc. atraves de TIM_LLM_PROVIDER.
    """

    # AOFERTA usa 120b — maior fidelidade no julgamento de oferta proativa.
    # PINJ usa 20b explicitamente (AT-15): prompt expandido com 11 exemplos e
    # 7 categorias torna a tarefa suficientemente estruturada para modelo leve.
    # Antes da reescrita do prompt (AT-03) PINJ usava 120b como compensação.
    # Demais rails seguem TIM_LLM_OCI_VARIANT.
    _TASK_OCI_VARIANT: dict[str, str] = {
        "AOFERTA": "120b",
        "PINJ": "20b",
    }

    def __init__(self) -> None:
        self._llms: dict[str, Any] = {}

    @property
    def use_mock(self) -> bool:
        """Le USE_MOCK_LLM dinamicamente.

        Era um atributo cacheado em __init__, mas como `_client` eh instanciado
        no import-time de output_sanitization.py, em alguns boots do uvicorn
        isso acontecia ANTES do dotenv carregar o .env — entao o cliente ficava
        preso em mock=true mesmo com USE_MOCK_LLM=false no .env. Como property,
        cada chamada le o env atual; o overhead eh desprezivel.
        """
        return os.getenv("USE_MOCK_LLM", "true").lower() == "true"

    def _ensure_llm(self, oci_variant: str | None = None) -> Any:
        cache_key = oci_variant or "default"
        cached = self._llms.get(cache_key)
        if cached is not None:
            return cached
        import dataclasses

        from agente_contas_tim.agent.infra.langchain.llm_factory import (
            create_langchain_llm,
        )
        from agente_contas_tim.config import AppConfig

        llm_config = AppConfig.from_env().llm
        if oci_variant and (llm_config.provider or "").strip().lower() == "oci":
            llm_config = dataclasses.replace(llm_config, oci_variant=oci_variant)
        llm = create_langchain_llm(llm_config)
        self._llms[cache_key] = llm
        return llm

    def classify(
        self,
        task: str,
        payload: dict,
        *,
        callbacks: list | None = None,
    ) -> dict:
        """Roteia uma task de guardrail para o LLM (ou mock).

        Contrato de retorno depende da task:
        - AOFERTA: {"allowed", "label", "reason", "score"} (JSON do prompt).
        - REVPREC: {"allowed", "label", "reason", "score"} (JSON do prompt).
        - OOS: {"allowed", "label"} (JSON do prompt).
        - TOXOUT: {"text": str} — texto reescrito sem trechos toxicos.

        `callbacks` (opcional) eh repassado via `config={"callbacks": ...}`
        para `llm.invoke`. Permite que o caller (ex.: loop._finalize_run)
        injete o `LangfuseCallbackHandler` para que o `ChatLLM` da reescrita
        apareca como span no Langfuse.
        """
        if self.use_mock:
            return self._mock_classify(task, payload)

        context_dict = payload.get("context") if isinstance(payload, dict) else None
        context_str = format_context_block(context_dict)
        if task == "AOFERTA":
            prompt = build_aoferta_prompt(payload["text"], context_str)
        elif task == "REVPREC":
            prompt = build_revprec_prompt(payload["text"], context_str)
        elif task == "OOS":
            prompt = build_oos_prompt(payload["text"], context_str)
        elif task == "TOXOUT":
            prompt = build_toxout_rewrite_prompt(payload["text"])
        elif task == "TOX":
            prompt = build_tox_prompt(payload["text"])

        # Segurança Extra
        elif task == "PINJ":
            prompt = build_pinj_prompt(payload["text"], context_str)
        elif task == "RAGSEC":
            prompt = build_ragsec_prompt(payload["text"], context_str)
        elif task == "DLEX_IN":
            prompt = build_dlex_in_prompt(payload["text"])
        elif task == "DLEX_OUT":
            prompt = build_dlex_out_prompt(payload["text"], context_str)
        elif task == "FALLBACK":
            prompt = build_fallback_prompt(
                payload["text"],
                guardrail_code=payload.get("guardrail_code"),
                guardrail_reason=payload.get("guardrail_reason"),
                context=payload.get("context"),
            )

        else:
            raise ValueError(f"Task nao suportada: {task}")

        from langchain_core.messages import HumanMessage

        from agente_contas_tim.agent.llm_gateway.invocation import (
            invoke_llm_with_config,
            invoke_llm_with_leak_retry,
        )

        llm = self._ensure_llm(self._TASK_OCI_VARIANT.get(task))

        messages = [HumanMessage(content=prompt)]
        # AOFERTA / REVPREC / OOS retornam JSON estruturado — qualquer texto
        # tipo "The user is..." dentro dele é semanticamente legítimo, então
        # a inspeção em modo json não dispara falsos positivos. TOXOUT
        # devolve texto livre, então usa modo text.
        inspection_mode = "text" if task == "TOXOUT" else "json"

        def _invoke_once(_prior: list[Any]) -> Any:
            return invoke_llm_with_config(llm, messages, callbacks=callbacks)

        response = invoke_llm_with_leak_retry(
            _invoke_once, inspection_mode=inspection_mode
        )
        text = getattr(response, "content", None)
        if isinstance(text, list):
            text = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in text
            )
        text = (text or "").strip()

        if task == "TOXOUT":
            return {"text": text}

        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return {"allowed": False, "label": "ERROR", "reason": text}

    def _mock_classify(self, task: str, payload: dict) -> dict:
        """Fallback local para dev/teste com razão de negócio real no retorno."""
        raw = payload.get("text") or ""
        text = raw.lower()

        def first_substring(triggers):
            for trigger in triggers:
                if trigger and trigger in text:
                    return trigger
            return None

        def first_regex(patterns):
            for pattern in patterns:
                if re.search(pattern, raw, re.IGNORECASE):
                    return pattern
            return None

        if task == "AOFERTA":
            trigger = first_substring(_AOFERTA_TRIGGERS)
            indevida = trigger is not None
            return {
                "allowed": not indevida,
                "label": "OFERTA_PROATIVA_INDEVIDA" if indevida else "OFERTA_OK",
                "reason": f"oferta proativa detectada pelo marcador '{trigger}'" if indevida else "não há oferta proativa não solicitada no trecho avaliado",
                "score": 0 if indevida else 10,
                "detector": "local_fallback",
                "matched": trigger,
            }

        if task == "REVPREC":
            marker = first_substring(_REVPREC_MARKERS)
            blocked = marker is not None
            return {
                "allowed": not blocked,
                "label": "PREMATURA" if blocked else "OK",
                "reason": f"verbalização prematura detectada pelo marcador '{marker}' antes de confirmação/evidência operacional" if blocked else "não há promessa de execução operacional antes de confirmação ou evidência",
                "score": 0 if blocked else 10,
                "detector": "local_fallback",
                "matched": marker,
            }

        if task == "OOS":
            trigger = first_substring(_OOS_MOCK_TRIGGERS)
            blocked = trigger is not None
            return {
                "allowed": not blocked,
                "label": "OUT_OF_SCOPE" if blocked else "IN_SCOPE",
                "reason": f"tema fora do escopo de contas/faturas TIM detectado pelo marcador '{trigger}'" if blocked else "mensagem permanece dentro do escopo esperado de atendimento",
                "score": 0 if blocked else 10,
                "detector": "local_fallback",
                "matched": trigger,
            }

        if task == "TOXOUT":
            cleaned = raw
            matched = []
            for pattern in _TOXOUT_MOCK_PATTERNS:
                if re.search(pattern, cleaned, flags=re.IGNORECASE):
                    matched.append(pattern)
                cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
            cleaned = " ".join(cleaned.split())
            return {
                "text": cleaned,
                "reason": "toxicidade removida do output por blocklist local" if matched else "nenhuma toxicidade encontrada no output",
                "detector": "local_fallback",
                "matched": matched,
            }

        if task == "TOX":
            patterns = (
                r"\b(idiota|imbecil|burro|est[uú]pido|in[uú]til|maldito|miser[aá]vel|incompetente)\b",
                r"\b(filho da puta|fdp|vai se foder|vai tomar no cu)\b",
                r"\b(idiots?|stupid|useless|moron)\b",
            )
            pattern = first_regex(patterns)
            blocked = pattern is not None
            return {
                "allowed": not blocked,
                "label": "TOXICO" if blocked else "NORMAL",
                "reason": f"toxicidade direta detectada por padrão '{pattern}'" if blocked else "não há ofensa, ameaça ou toxicidade direta no texto avaliado",
                "score": 0 if blocked else 10,
                "detector": "local_fallback",
                "matched": pattern,
            }

        if task == "PINJ":
            patterns = (
                r"ignore (all )?(previous|prior) instructions",
                r"ignore todas as instru[cç][oõ]es",
                r"esque[cç]a (as|todas as) regras",
                r"reveal (the )?(system prompt|hidden prompt|instructions)",
                r"mostre (o )?(prompt|system prompt|prompt oculto|instru[cç][oõ]es internas)",
                r"developer message",
                r"system message",
                r"modo desenvolvedor",
                r"bypass",
                r"DAN\b",
            )
            pattern = first_regex(patterns)
            blocked = pattern is not None
            return {
                "allowed": not blocked,
                "label": "PROMPT_INJECTION" if blocked else "OK",
                "reason": f"prompt injection/jailbreak detectado por padrão '{pattern}'" if blocked else "não há tentativa de sobrescrever instruções, extrair prompt ou burlar políticas",
                "score": 0 if blocked else 10,
                "detector": "local_fallback",
                "matched": pattern,
            }

        if task in {"RAGSEC", "DLEX_IN", "DLEX_OUT"}:
            return {
                "allowed": True,
                "label": "OK",
                "reason": f"{task} sem indício de violação no fallback local",
                "score": 5,
                "detector": "local_fallback",
                "matched": None,
            }

        return {"allowed": True, "label": "OK", "reason": f"{task} sem indício de violação no fallback local", "score": 5, "detector": "local_fallback"}
