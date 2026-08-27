from __future__ import annotations

from agent_framework.llm.structured_output import parse_json_object

import json
import logging
import re
from typing import Any, Mapping

logger = logging.getLogger(__name__)

_EMPTY_VALUES = (None, "", {}, [])


def _response_text(response: Any) -> str:
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        return str(response.get("content") or response.get("text") or response.get("answer") or "")
    return str(getattr(response, "content", None) or getattr(response, "text", None) or response)


def _coerce(value: Any, declared_type: Any) -> Any:
    if value in _EMPTY_VALUES:
        return None
    type_name = str(declared_type or "string").strip().lower()
    try:
        if type_name in {"integer", "int"}:
            return int(value)
        if type_name in {"number", "float", "double"}:
            return float(value)
        if type_name in {"boolean", "bool"}:
            if isinstance(value, bool):
                return value
            normalized = str(value).strip().lower()
            if normalized in {"true", "1", "yes", "sim"}:
                return True
            if normalized in {"false", "0", "no", "não", "nao"}:
                return False
            return None
        if type_name in {"array", "list"}:
            return value if isinstance(value, list) else [value]
        if type_name in {"object", "dict", "map"}:
            return value if isinstance(value, dict) else None
        return str(value).strip()
    except (TypeError, ValueError):
        return None


def parse_transaction_confirmation(text: str) -> str | None:
    """Recognize an explicit confirmation/rejection before intent-shift routing.

    This is intentionally small and domain-neutral. Parameter interpretation is
    LLM-only; confirmation remains a deterministic control token so an explicit
    yes/no cannot be reclassified as a new intent.
    """
    normalized = " ".join(str(text or "").strip().lower().split())
    normalized = re.sub(r"[.!?]+$", "", normalized).strip()
    if normalized in {
        "sim", "confirmo", "sim, confirmo", "pode fazer", "pode prosseguir",
        "sim, desejo", "sim, desejo trocar", "sim, confirmo a devolução",
        "sim, confirmo a troca",
    }:
        return "confirm"
    if normalized in {"não", "nao", "cancelar", "cancele", "não confirmo", "nao confirmo"}:
        return "reject"
    return None


async def extract_transaction_parameters(
    llm: Any,
    *,
    text: str,
    tool_name: str,
    missing_parameters: list[str],
    known_arguments: Mapping[str, Any] | None = None,
    parameter_schema: Mapping[str, Any] | None = None,
    tool_description: str | None = None,
) -> dict[str, Any]:
    """Extract values for pending transactional parameters using the LLM only.

    This component intentionally contains no domain/entity regexes and no
    knowledge of parameter names such as ``order_id`` or ``reason``.  The
    transaction runtime supplies the pending parameter names and optional schema;
    the LLM only interprets the current user turn.  State/control-flow decisions
    remain deterministic outside this function.
    """
    pending = [str(name) for name in (missing_parameters or []) if str(name).strip()]
    message = str(text or "").strip()
    if not pending or not message or llm is None:
        return {}

    schema = dict(parameter_schema or {})
    known = {
        str(key): value
        for key, value in dict(known_arguments or {}).items()
        if value not in _EMPTY_VALUES and str(key) not in pending
    }
    field_spec = {
        name: {
            "type": schema.get(name, "string") if not isinstance(schema.get(name), dict) else schema.get(name, {}).get("type", "string"),
            "description": None if not isinstance(schema.get(name), dict) else schema.get(name, {}).get("description"),
        }
        for name in pending
    }
    output_shape = {name: None for name in pending}
    prompt = (
        "Você extrai parâmetros PENDENTES de uma transação ativa. "
        "Sua única tarefa é interpretar a mensagem atual e devolver valores para os parâmetros pendentes. "
        "Não decida roteamento, intenção, confirmação ou execução da transação.\n\n"
        "REGRAS OBRIGATÓRIAS:\n"
        "1. Extraia SOMENTE parâmetros listados em pending_parameters.\n"
        "2. Não invente valores e não transforme uma nova solicitação/intenção do usuário em valor de parâmetro.\n"
        "3. Se nenhum parâmetro pendente foi realmente informado, devolva null para todos.\n"
        "4. Se houver apenas um parâmetro pendente, uma resposta contendo apenas um valor pode ser associada a ele quando isso for semanticamente inequívoco.\n"
        "5. Se houver vários parâmetros pendentes, extraia todos os que estiverem presentes no mesmo turno.\n"
        "6. O nome do parâmetro não precisa aparecer literalmente na fala. Associe semanticamente o valor usando o nome da transação e os metadados disponíveis para cada campo.\n"
        "7. Para cada parâmetro, considere o nome técnico, o tipo quando disponível e principalmente a descrição semântica quando disponível. A ausência de tipo ou descrição NÃO impede a extração.\n"
        "8. Se a mensagem deixar clara a correspondência entre um trecho e um parâmetro, preencha-o mesmo que o usuário não cite o nome técnico do campo.\n"
        "9. Não use conhecimento externo para completar valores ausentes e não transforme aproximações ou suposições em fatos.\n"
        "10. Em caso de dúvida razoável sobre a correspondência ou o valor, prefira null.\n"
        "11. Responda SOMENTE JSON válido, sem markdown, sem explicação e sem chaves extras.\n\n"
        f"transaction_tool: {tool_name}\n"
        f"transaction_description: {tool_description or ''}\n"
        f"pending_parameters: {json.dumps(pending, ensure_ascii=False)}\n"
        f"parameter_schema: {json.dumps(field_spec, ensure_ascii=False, default=str)}\n"
        f"known_arguments: {json.dumps(known, ensure_ascii=False, default=str)}\n"
        f"user_message: {message}\n"
        f"Formato obrigatório: {json.dumps(output_shape, ensure_ascii=False)}"
    )

    try:
        response = await llm.ainvoke(
            [{"role": "user", "content": prompt}],
            profile_name="transaction_parameter_extraction",
            component_name="transaction_parameter_extraction",
            generation_name="llm.transaction_parameter_extraction",
            temperature=0.0,
            max_tokens=max(120, min(500, 80 + 60 * len(pending))),
        )
    except TypeError:
        # Compatibilidade com doubles/testes e providers mínimos que aceitam
        # apenas messages.
        response = await llm.ainvoke([{"role": "user", "content": prompt}])
    except Exception as exc:
        logger.warning(
            "transaction.parameter.llm_extract_failed tool=%s pending=%s error=%s",
            tool_name,
            pending,
            exc,
        )
        return {}

    raw = _response_text(response).strip()
    try:
        payload = parse_json_object(raw)
    except (TypeError, ValueError):
        logger.warning(
            "transaction.parameter.llm_invalid_structured_output tool=%s pending=%s raw=%r",
            tool_name,
            pending,
            raw[:240],
        )
        return {}
    if not isinstance(payload, dict):
        return {}

    extracted: dict[str, Any] = {}
    for name in pending:
        value = payload.get(name)
        declared = field_spec.get(name, {}).get("type", "string")
        coerced = _coerce(value, declared)
        if coerced not in _EMPTY_VALUES:
            extracted[name] = coerced

    logger.info(
        "transaction.parameter.llm_extracted tool=%s pending=%s consumed=%s",
        tool_name,
        pending,
        sorted(extracted),
    )
    return extracted
