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


async def reconcile_transaction_parameters(
    llm: Any,
    *,
    text: str,
    tool_name: str,
    parameter_names: list[str],
    known_arguments: Mapping[str, Any] | None = None,
    parameter_schema: Mapping[str, Any] | None = None,
    tool_description: str | None = None,
    conversational_context: str | None = None,
) -> dict[str, Any]:
    """Rebuild a coherent parameter set from text, newest to oldest.

    The framework is intentionally field/domain neutral.  Meaning comes from the
    declarative tool schema (normally tools.yaml) plus the conversation text.
    The LLM may resolve a field, preserve a previously known value, explicitly
    clear a stale value whose context was superseded, or leave a field unresolved.
    Returned provenance is interpretive metadata only; authoritative business
    validation still belongs to the configured pre-validation/tool layer.
    """
    names = [str(name) for name in (parameter_names or []) if str(name).strip()]
    message = str(text or "").strip()
    if not names or not message or llm is None:
        return {"values": {}, "decisions": {}, "provenance": {}, "clear_fields": []}

    schema = dict(parameter_schema or {})
    known = {
        str(key): value
        for key, value in dict(known_arguments or {}).items()
        if value not in _EMPTY_VALUES
    }
    field_spec = {
        name: {
            "type": schema.get(name, "string") if not isinstance(schema.get(name), dict) else schema.get(name, {}).get("type", "string"),
            "description": None if not isinstance(schema.get(name), dict) else schema.get(name, {}).get("description"),
        }
        for name in names
    }
    output_shape = {
        "fields": {
            name: {"decision": "resolved|preserve|clear|unresolved", "value": None, "source": "current|history:N|state"}
            for name in names
        }
    }
    prompt = (
        "Você é o conciliador temporal de parâmetros de uma transação ativa. "
        "Reconstrua UM CONJUNTO COERENTE de parâmetros; não extraia cada campo de forma isolada. "
        "Não decida roteamento, confirmação nem execução.\n\n"
        "CONTRATO OBRIGATÓRIO:\n"
        "1. O significado de cada campo vem EXCLUSIVAMENTE de parameter_schema e transaction_description, considerando principalmente a descrição semântica quando disponível. O framework não conhece conceitos de domínio por nome de campo.\n"
        "2. A ausência de tipo ou descrição NÃO impede a extração quando o restante do contrato e o texto forem semanticamente suficientes.\n"
        "3. A busca textual é temporal, em ordem decrescente: user_message é a fonte mais nova; depois conversational_context já vem do texto mais novo para o mais antigo.\n"
        "3. Textos do usuário e textos explicativos do assistente podem ser usados para interpretar referências e relações entre campos. Não trate texto do contexto como uma nova afirmação do cliente; eles são contexto, não evidência autoritativa de negócio.\n"
        "4. Para cada campo escolha: resolved = um texto determina novo valor; preserve = nenhum texto mais novo invalida o valor conhecido; clear = existe mudança textual mais nova que torna o valor conhecido incompatível/sem vínculo seguro com o novo contexto e ainda não há substituto; unresolved = não há valor conhecido nem candidato textual seguro.\n"
        "5. Se uma fonte mais nova muda uma entidade, objeto, escopo ou outro contexto que dava sentido a campos extraídos anteriormente, REAVALIE os demais campos como conjunto. Não combine automaticamente um atributo antigo com um contexto novo só porque ambos existem.\n"
        "6. Um valor de texto anterior pode continuar válido após uma mudança somente quando os textos, considerados em conjunto, sustentarem de forma inequívoca que ele ainda pertence ao contexto mais recente. Caso contrário use clear para o campo dependente.\n"
        "7. Se a nova menção é inválida no mundo real, NÃO volte silenciosamente ao valor antigo. Ainda assim devolva o candidato textual mais recente como resolved; a pre-validation autoritativa é responsável por rejeitá-lo.\n"
        "8. known_arguments é fallback de estado. Use preserve somente quando nenhum texto mais novo o contradiz ou rompe sua associação contextual.\n"
        "9. Uma expressão só pode preencher um campo se satisfizer semanticamente type/description desse campo. Não transfira um trecho para outro campo apenas por proximidade lexical.\n"
        "10. Se um texto recente corrige explicitamente informação anterior, a correção prevalece para os campos que o schema permite inferir; os demais devem ser reavaliados quanto à coerência com a correção.\n"
        "11. Em ambiguidade razoável, prefira clear/unresolved a inventar uma associação. Em caso de dúvida razoável sobre a correspondência ou o valor, prefira null.\n"
        "12. Responda SOMENTE JSON válido no formato pedido, sem markdown e sem chaves extras.\n\n"
        f"transaction_tool: {tool_name}\n"
        f"transaction_description: {tool_description or ''}\n"
        f"parameter_names: {json.dumps(names, ensure_ascii=False)}\n"
        f"pending_parameters: {json.dumps(names, ensure_ascii=False)}\n"
        f"parameter_schema: {json.dumps(field_spec, ensure_ascii=False, default=str)}\n"
        f"known_arguments: {json.dumps(known, ensure_ascii=False, default=str)}\n"
        "conversation_sources_newest_to_oldest:\n"
        f"user_message: {message}\n"
        f"conversational_context: {str(conversational_context or '').strip()}\n"
        f"Formato obrigatório: {json.dumps(output_shape, ensure_ascii=False)}"
    )

    try:
        response = await llm.ainvoke(
            [{"role": "user", "content": prompt}],
            profile_name="transaction_parameter_extraction",
            component_name="transaction_parameter_extraction",
            generation_name="llm.transaction_parameter_extraction",
            temperature=0.0,
        )
    except TypeError:
        response = await llm.ainvoke([{"role": "user", "content": prompt}])
    except Exception as exc:
        logger.warning("transaction.parameter.reconcile_failed tool=%s fields=%s error=%s", tool_name, names, exc)
        return {"values": {}, "decisions": {}, "provenance": {}, "clear_fields": []}

    raw = _response_text(response).strip()
    try:
        payload = parse_json_object(raw)
    except (TypeError, ValueError):
        logger.warning("transaction.parameter.reconcile_invalid_output tool=%s raw=%r", tool_name, raw[:240])
        return {"values": {}, "decisions": {}, "provenance": {}, "clear_fields": []}
    if not isinstance(payload, dict):
        return {"values": {}, "decisions": {}, "provenance": {}, "clear_fields": []}

    # Backward compatibility with existing providers/test doubles that return a
    # flat {field: value} object. Non-null flat values mean ``resolved``.
    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else None
    if fields is None:
        fields = {}
        for name in names:
            flat_value = payload.get(name)
            if flat_value in _EMPTY_VALUES:
                decision = "preserve" if name in known else "unresolved"
                source = "state" if decision == "preserve" else ""
            else:
                decision = "resolved"
                source = "current"
            fields[name] = {"decision": decision, "value": flat_value, "source": source}

    values: dict[str, Any] = {}
    decisions: dict[str, str] = {}
    provenance: dict[str, str] = {}
    clear_fields: list[str] = []
    for name in names:
        item = fields.get(name) if isinstance(fields, dict) else None
        if not isinstance(item, dict):
            item = {"decision": "unresolved", "value": None, "source": ""}
        decision = str(item.get("decision") or "unresolved").strip().lower()
        if decision not in {"resolved", "preserve", "clear", "unresolved"}:
            decision = "unresolved"
        decisions[name] = decision
        source = str(item.get("source") or "").strip()
        if source:
            provenance[name] = source
        if decision == "clear":
            clear_fields.append(name)
            continue
        if decision == "preserve":
            if name in known:
                values[name] = known[name]
            continue
        if decision != "resolved":
            continue
        declared = field_spec.get(name, {}).get("type", "string")
        coerced = _coerce(item.get("value"), declared)
        if coerced not in _EMPTY_VALUES:
            values[name] = coerced
        else:
            decisions[name] = "unresolved"

    logger.info(
        "transaction.parameter.reconciled tool=%s decisions=%s resolved=%s clear=%s provenance=%s",
        tool_name, decisions, sorted(values), clear_fields, provenance,
    )
    return {"values": values, "decisions": decisions, "provenance": provenance, "clear_fields": clear_fields}


async def extract_transaction_parameters(
    llm: Any,
    *,
    text: str,
    tool_name: str,
    missing_parameters: list[str],
    known_arguments: Mapping[str, Any] | None = None,
    parameter_schema: Mapping[str, Any] | None = None,
    tool_description: str | None = None,
    conversational_context: str | None = None,
) -> dict[str, Any]:
    """Compatibility facade returning only resolved candidates.

    New runtime code should use :func:`reconcile_transaction_parameters` when it
    needs preserve/clear/provenance decisions.  Keeping this facade avoids
    breaking routers and existing extensions that only need candidate extraction.
    """
    result = await reconcile_transaction_parameters(
        llm,
        text=text,
        tool_name=tool_name,
        parameter_names=missing_parameters,
        known_arguments=known_arguments,
        parameter_schema=parameter_schema,
        tool_description=tool_description,
        conversational_context=conversational_context,
    )
    return dict(result.get("values") or {})
