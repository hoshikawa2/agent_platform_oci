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


async def extract_current_transaction_parameters(
    llm: Any,
    *,
    text: str,
    tool_name: str,
    missing_parameters: list[str],
    known_arguments: Mapping[str, Any] | None = None,
    parameter_schema: Mapping[str, Any] | None = None,
    tool_description: str | None = None,
) -> dict[str, Any]:
    """Extract only values explicitly present in the current user utterance.

    This is deliberately narrower than temporal reconciliation: no history, no
    cross-turn inference and no routing. Spoken numeric expressions are normalized
    according to the declared numeric type, while textual fields must satisfy the
    schema description in the current message itself.
    """
    names = [str(x) for x in (missing_parameters or []) if str(x).strip()]
    message = str(text or "").strip()
    if not names or not message or llm is None:
        return {}
    schema = dict(parameter_schema or {})
    field_spec = {
        name: {
            "type": schema.get(name, "string") if not isinstance(schema.get(name), dict) else schema.get(name, {}).get("type", "string"),
            "description": None if not isinstance(schema.get(name), dict) else schema.get(name, {}).get("description"),
        }
        for name in names
    }
    output = {name: None for name in names}
    prompt = (
        "Extraia SOMENTE parâmetros explicitamente expressos na mensagem atual do usuário. "
        "Não use histórico, não complete referências elípticas com conhecimento anterior e não invente valores. "
        "Use exclusivamente type/description do schema para decidir se um trecho preenche um campo. "
        "Para campos numéricos, normalize também números falados por extenso para número (por exemplo uma expressão monetária falada deve virar number). "
        "Para campos textuais que exigem uma entidade concreta, uma referência apenas por valor/posição não preenche o campo. "
        "Retorne SOMENTE JSON válido com exatamente as chaves pedidas; use null quando ausente ou ambíguo.\n"
        f"tool: {tool_name}\n"
        f"tool_description: {tool_description or ''}\n"
        f"known_arguments: {json.dumps(dict(known_arguments or {}), ensure_ascii=False, default=str)}\n"
        f"parameter_schema: {json.dumps(field_spec, ensure_ascii=False, default=str)}\n"
        f"current_user_message: {message}\n"
        f"Formato: {json.dumps(output, ensure_ascii=False)}"
    )
    try:
        response = await llm.ainvoke(
            [{"role": "user", "content": prompt}],
            profile_name="transaction_parameter_extraction",
            component_name="transaction_parameter_extraction",
            generation_name="llm.transaction_parameter_current_only",
            temperature=0.0,
        )
    except TypeError:
        response = await llm.ainvoke([{"role": "user", "content": prompt}])
    except Exception as exc:
        logger.warning("transaction.parameter.current_extract_failed tool=%s fields=%s error=%s", tool_name, names, exc)
        return {}
    raw = _response_text(response).strip()
    try:
        payload = parse_json_object(raw)
    except (TypeError, ValueError):
        logger.warning("transaction.parameter.current_extract_invalid tool=%s raw=%r", tool_name, raw[:240])
        return {}
    if not isinstance(payload, dict):
        return {}
    values: dict[str, Any] = {}
    for name in names:
        value = payload.get(name)
        declared = field_spec.get(name, {}).get("type", "string")
        coerced = _coerce(value, declared)
        if coerced not in _EMPTY_VALUES:
            values[name] = coerced
    return values


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

    def _anchor_tokens(value: Any) -> list[str]:
        """Return generic textual variants for a known scalar anchor."""
        if value in _EMPTY_VALUES:
            return []
        raw = str(value).strip().lower()
        tokens = {raw}
        try:
            number = float(str(value).replace(",", "."))
            tokens.add(f"{number:.2f}")
            tokens.add(f"{number:.2f}".replace(".", ","))
            if number.is_integer():
                tokens.add(str(int(number)))
        except (TypeError, ValueError):
            pass
        return [token for token in tokens if token]

    def _anchor_relation_candidates(context: str, arguments: Mapping[str, Any]) -> list[str]:
        """Surface history fragments related to any already-known parameter.

        This is not a second reconciliation pass and does not resolve anything
        deterministically.  It only structures the SAME temporal scan so the LLM
        can use known/current fields as cross-field anchors while reconciling all
        pending fields coherently in one call.
        """
        if not context or not arguments:
            return []
        # Keep role/history prefixes but split long assistant explanations into
        # smaller semantic clauses (bullets/semicolons) so one anchor is not lost
        # among many unrelated entity/value pairs.
        fragments: list[str] = []
        for raw_line in context.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parts = [part.strip() for part in re.split(r"\s*\*\s*|\s*;\s*", line) if part.strip()]
            fragments.extend(parts or [line])

        candidates: list[str] = []
        for field_name, field_value in arguments.items():
            variants = _anchor_tokens(field_value)
            if not variants:
                continue
            for fragment in fragments:
                low = fragment.lower()
                if any(token in low for token in variants):
                    candidates.append(f"anchor[{field_name}={field_value}]: {fragment}")
        return list(dict.fromkeys(candidates))

    def _structured_evidence_blocks(context: str, arguments: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Represent the same bounded history as explicit message evidence blocks.

        The reconciler remains a single LLM call.  This helper only prevents role,
        recency and anchor relationships from being hidden inside one prose blob.
        It is fully domain-neutral: field meaning still comes from parameter_schema.
        """
        blocks: list[dict[str, Any]] = []
        current_role = "other"
        current_lines: list[str] = []
        rank = 0

        def flush() -> None:
            nonlocal rank, current_lines, current_role
            if not current_lines:
                return
            text_block = " ".join(x.strip() for x in current_lines if x.strip()).strip()
            current_lines = []
            if not text_block:
                return

            # A single assistant message often contains a list of independent
            # entity/attribute relations (for example several invoice items).
            # Keeping the whole answer as one evidence block makes an otherwise
            # exact anchor ambiguous because every entity in the list competes
            # inside the same block.  Segment LOCAL relations while preserving
            # the original role, priority and message recency.  This is still the
            # same temporal reconciliation and the same single LLM call.
            fragments = [
                frag.strip(" \t-•")
                for frag in re.split(
                    r"\s+(?:\*|•)\s+|\s*;\s+|\s+(?=\d+[.)]\s+)",
                    text_block,
                )
                if frag.strip(" \t-•")
            ]
            if not fragments:
                fragments = [text_block]

            rank += 1
            role_priority = 3 if current_role == "assistant" else 4 if current_role == "user" else 5
            for fragment_index, fragment in enumerate(fragments, start=1):
                anchor_matches: list[dict[str, Any]] = []
                low = fragment.lower()
                for field_name, field_value in arguments.items():
                    variants = _anchor_tokens(field_value)
                    matched = [token for token in variants if token in low]
                    if matched:
                        anchor_matches.append({
                            "field": str(field_name),
                            "value": field_value,
                            "matched_tokens": matched,
                        })
                blocks.append({
                    "priority": role_priority,
                    "recency": rank,
                    "fragment": fragment_index,
                    "role": current_role,
                    "text": fragment,
                    "anchor_matches": anchor_matches,
                })

        for raw_line in str(context or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            low = line.lower()
            # Priority-view section headers are metadata, not conversational text.
            if low.startswith("priority_3_previous_assistant"):
                flush(); current_role = "assistant"; continue
            if low.startswith("priority_4_previous_user"):
                flush(); current_role = "user"; continue
            if low.startswith("priority_5_other"):
                flush(); current_role = "other"; continue
            payload = line.split(": ", 1)[1] if line.startswith("history:") and ": " in line else line
            plow = payload.lower().lstrip()
            detected = None
            if plow.startswith(("assistant:", "agente:")):
                detected = "assistant"
            elif plow.startswith(("user:", "cliente:")):
                detected = "user"
            elif plow.startswith("system:"):
                detected = "other"
            if detected is not None:
                flush()
                current_role = detected
                payload = payload.split(":", 1)[1].strip() if ":" in payload else payload
            current_lines.append(payload)
        flush()
        return blocks

    context_text = str(conversational_context or "").strip()
    anchor_relations = _anchor_relation_candidates(context_text, known)
    evidence_blocks = _structured_evidence_blocks(context_text, known)
    missing_initial = [name for name in names if name not in known]

    # Field-targeted views do not resolve parameters and do not add another LLM
    # pass. They expose the SAME local evidence blocks next to the declarative
    # semantics of each still-missing field so the single temporal reconciliation
    # call can correlate anchors with the correct schema-defined target instead of
    # rediscovering that mapping inside a large generic JSON blob. No field names
    # or domain concepts are hardcoded here.
    anchored_blocks = [block for block in evidence_blocks if block.get("anchor_matches")]
    field_evidence_views = {
        name: {
            "field_spec": field_spec.get(name, {}),
            "anchored_evidence_blocks": anchored_blocks,
        }
        for name in missing_initial
    }

    reconciliation_focus = {
        "current_user_message": message,
        "known_parameters": known,
        "missing_parameters": missing_initial,
        "missing_field_views": field_evidence_views,
    }

    prompt = (
        "FOCO PRINCIPAL DA RECONCILIAÇÃO (examine isto antes de qualquer contexto secundário):\n"
        f"reconciliation_focus: {json.dumps(reconciliation_focus, ensure_ascii=False, default=str)}\n"
        "Se um campo faltante tiver um único evidence_block ancorado semanticamente compatível com seu field_spec, resolva-o; use unresolved somente em ambiguidade real.\n\n"
        "Você é o conciliador temporal de parâmetros de uma transação ativa. "
        "Faça UMA ÚNICA VARREDURA TEMPORAL e reconstrua UM CONJUNTO COERENTE de parâmetros. "
        "Todos os campos conhecidos e faltantes devem ser avaliados juntos; não execute uma busca isolada por campo e não faça uma segunda etapa de fallback. "
        "Não decida roteamento, confirmação nem execução.\n\n"
        "CONTRATO OBRIGATÓRIO:\n"
        "1. O significado de cada campo vem EXCLUSIVAMENTE de parameter_schema e transaction_description, principalmente a descrição semântica quando disponível. O framework não conhece conceitos de domínio por nome de campo.\n"
        "2. A ausência de tipo ou descrição NÃO impede a extração nem a resolução quando o restante do contrato e o contexto forem semanticamente suficientes.\n"
        "3. A resolução deve obedecer ESTA PRIORIDADE, sem inverter níveis: (1) informação explicitamente fornecida pelo usuário na mensagem atual e semanticamente compatível com o schema; (2) parâmetros já conhecidos/validados da transação; (3) respostas anteriores do assistente que apresentem relações locais entre parâmetros/atributos e que possam ter sido apoiadas por tool/evidence; (4) falas anteriores do usuário; (5) demais contexto conversacional.\n"
        "4. Dentro de cada nível histórico, preserve a ordem temporal decrescente (mais novo -> mais antigo). Nunca escolha fonte de prioridade menor quando uma fonte de prioridade maior resolve o mesmo campo de forma coerente.\n"
        "5. known_arguments contém o estado parcial já coletado/validado. Trate CADA parâmetro conhecido, independentemente de nome ou tipo, como possível ÂNCORA para resolver QUALQUER outro campo faltante no histórico. O significado e a compatibilidade de cada âncora vêm exclusivamente do parameter_schema. Use múltiplas âncoras simultaneamente quando disponíveis.\n"
        "6. anchor_relation_candidates são apenas recortes do MESMO histórico que contêm representações de parâmetros conhecidos; eles servem para facilitar a correlação entre campos dentro desta única varredura. Não são uma segunda fonte, não têm prioridade própria e não autorizam inventar relações.\n"
        "7. Quando uma âncora conhecida aparecer em um mesmo contexto local com uma ou mais informações semanticamente compatíveis com campos faltantes, use essa relação local para reconciliar TODOS os campos faltantes que puderem ser resolvidos de forma coerente na mesma resposta. Não pressuponha quais tipos de campo devem coexistir; siga apenas o schema e o contexto.\n"
        "8. Texto anterior do assistente é CONTEXTO INTERPRETATIVO, não evidência autoritativa: pode fornecer relações locais entre quaisquer parâmetros/atributos definidos pelo schema, mas todo candidato continua sujeito à pre-validation/tool de negócio. Não descarte uma relação apenas por estar na fala do assistente. Não trate texto do contexto como uma nova afirmação do cliente.\n"
        "9. Para cada campo escolha: resolved = texto/contexto determina novo valor; preserve = o valor conhecido continua coerente; clear = contexto mais novo rompe sua associação e não há substituto seguro; unresolved = não há candidato seguro.\n"
        "10. Se uma fonte mais nova muda o contexto semântico que dava sentido a campos anteriores, REAVALIE os demais campos como conjunto. Não combine automaticamente informação antiga com contexto novo.\n"
        "11. Se a nova menção é inválida no mundo real, NÃO volte silenciosamente ao valor antigo. Devolva o candidato textual mais recente como resolved e deixe a pre-validation autoritativa rejeitá-lo.\n"
        "12. Uma expressão só pode preencher um campo se satisfizer semanticamente type/description desse campo. Não transfira um trecho para outro campo apenas por proximidade lexical.\n"
        "13. Se o usuário corrige explicitamente informação anterior, a correção prevalece nos campos compatíveis e os demais devem ser reavaliados quanto à coerência.\n"
        "14. unresolved é ÚLTIMO RECURSO. Antes de devolver unresolved para um campo faltante, você DEVE verificar todos os evidence_blocks na ordem de prioridade e recência e todas as anchor_relation_candidates. Se existir uma única interpretação semanticamente compatível com type/description do campo, resolva-a.\n"
        "15. Se um parâmetro conhecido aparecer como anchor_match em um evidence_block e o MESMO bloco contiver uma única informação semanticamente compatível com um campo faltante segundo o schema, use a relação para resolved desse campo; não devolva unresolved apenas porque a informação foi apresentada pelo assistente.\n"
        "16. Se não houver âncora útil, mas uma fonte histórica de prioridade 3 ou 4 contiver explicitamente uma informação que satisfaça semanticamente um campo faltante segundo o schema e não houver candidato concorrente de prioridade maior, resolva esse campo. Isso cobre referências posteriores em que o usuário omite um atributo porque ele já estava explícito no diálogo.\n"
        "17. field_evidence_views reorganiza os MESMOS evidence_blocks ancorados por cada campo ainda faltante e coloca ao lado a semântica declarativa desse campo. Para cada campo faltante, examine obrigatoriamente essa visão antes de unresolved. Se um bloco ancorado contiver uma única informação compatível com field_spec e não houver concorrente de prioridade/recência maior, retorne resolved. Essa visão não é uma nova fonte nem uma segunda etapa.\n"
        "18. Em ambiguidade REAL — dois ou mais candidatos semanticamente plausíveis sem desempate por prioridade, recência ou âncora — prefira clear/unresolved a inventar uma associação. Em caso de dúvida razoável sobre a correspondência ou o valor, prefira null/unresolved conforme o formato de saída.\n"
        "19. Responda SOMENTE JSON válido no formato pedido, sem markdown e sem chaves extras.\n\n"
        f"transaction_tool: {tool_name}\n"
        f"transaction_description: {tool_description or ''}\n"
        f"parameter_names: {json.dumps(names, ensure_ascii=False)}\n"
        f"known_parameters: {json.dumps(known, ensure_ascii=False, default=str)}\n"
        f"missing_parameters: {json.dumps(missing_initial, ensure_ascii=False)}\n"
        f"pending_parameters: {json.dumps(names, ensure_ascii=False)}\n"
        f"parameter_schema: {json.dumps(field_spec, ensure_ascii=False, default=str)}\n"
        f"anchor_relation_candidates: {json.dumps(anchor_relations, ensure_ascii=False, default=str)}\n"
        f"evidence_blocks: {json.dumps(evidence_blocks, ensure_ascii=False, default=str)}\n"
        f"field_evidence_views: {json.dumps(field_evidence_views, ensure_ascii=False, default=str)}\n"
        "conversation_sources_newest_to_oldest:\n"
        f"priority_1_current_user_message: {message}\n"
        f"user_message: {message}\n"
        f"prioritized_conversational_context: {context_text}\n"
        "RELEMBRE O FOCO PRINCIPAL: examine reconciliation_focus.missing_field_views antes de unresolved. "
        "Um bloco ancorado único e semanticamente compatível deve produzir resolved, independentemente do papel assistant/user, respeitada a prioridade declarada.\n"
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

    # Structural candidates are intentionally NOT resolved values.  They are only
    # fallback material for a configured authoritative pre-validator.  This lets
    # the runtime carry a unique local evidence fragment (or, when no anchor
    # exists, a single prior user utterance) to domain validation without letting
    # the framework invent/canonicalize business entities.
    structural_candidates: dict[str, Any] = {}
    candidate_provenance: dict[str, str] = {}
    # For a field that was already missing before reconciliation, ``clear`` has
    # no distinct state effect: there is no prior value to invalidate. Treat it
    # as unresolved *only for structural-candidate fallback* so a unique anchored
    # history fragment can still be offered to the configured authoritative
    # pre-validator. This does not promote the fragment to a resolved value and
    # does not change ``clear_fields`` semantics for fields that were previously
    # populated.
    unresolved_missing = [
        name for name in missing_initial
        if decisions.get(name) in {"unresolved", "clear"} and name not in values
    ]
    anchored = [b for b in evidence_blocks if b.get("anchor_matches") and str(b.get("text") or "").strip()]
    prior_user = [
        b for b in evidence_blocks
        if int(b.get("priority") or 99) == 4 and str(b.get("text") or "").strip()
    ]
    for name in unresolved_missing:
        declared = str(field_spec.get(name, {}).get("type") or "string").strip().lower()
        if declared not in {"string", "str", "text"}:
            continue
        if len(anchored) == 1:
            structural_candidates[name] = str(anchored[0].get("text") or "").strip()
            candidate_provenance[name] = "unique_anchored_evidence_block"

    logger.info(
        "transaction.parameter.reconciled tool=%s decisions=%s resolved=%s clear=%s provenance=%s candidates=%s",
        tool_name, decisions, sorted(values), clear_fields, provenance, sorted(structural_candidates),
    )
    return {
        "values": values,
        "decisions": decisions,
        "provenance": provenance,
        "clear_fields": clear_fields,
        "candidates": structural_candidates,
        "candidate_provenance": candidate_provenance,
    }


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
