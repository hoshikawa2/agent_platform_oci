from __future__ import annotations

from contextlib import nullcontext
from decimal import Decimal, ROUND_HALF_UP
import logging
import os
import re
import unicodedata as ud
from typing import Any

_CENT = Decimal("0.01")
_GUARDRAIL_ACTION = "abrir_contestacao_cliente"
_GUARDRAIL_CODE = "CVAL"
_STRATEGIC_SERVICE_ALIASES = (
    "apple music",
    "deezer",
    "disney",
    "fuze",
    "forge",
    "hbo",
    "looke",
    "netflix",
    "paramount",
    "paramount+",
    "paramount plus",
    "tim cloud gaming",
    "youtube",
    "youtube premium",
)

logger = logging.getLogger(__name__)


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _parse_amount(value: str) -> Decimal | None:
    if not value:
        return None
    cleaned = (
        str(value)
        .replace("R$", "")
        .replace(" ", "")
        .replace(".", "")
        .replace(",", ".")
    )
    try:
        return Decimal(cleaned)
    except Exception:
        return None


def _decimal_from_any(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    return _parse_amount(str(value or ""))


def _first_decimal_from_mapping(data: dict[str, Any], *keys: str) -> Decimal | None:
    for key in keys:
        if key not in data:
            continue
        value = _decimal_from_any(data.get(key))
        if value is not None:
            return value
    return None


def _normalize_number_text(value: Any, *, default: str = "0") -> str:
    text = str(value).strip()
    if not text:
        return default
    cleaned = text.replace("R$", "").replace(" ", "")
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        normalized = format(Decimal(cleaned), "f")
    except Exception:
        return default
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or default


def _normalize_match_text(value: Any) -> str:
    text = re.sub(r"\s*\([^)]*\)", "", str(value or "")).strip()
    text = ud.normalize("NFKD", text)
    text = "".join(ch for ch in text if not ud.combining(ch))
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_same_plan_name(left: Any, right: Any) -> bool:
    left_key = _normalize_match_text(left)
    right_key = _normalize_match_text(right)
    if not left_key or not right_key:
        return False
    return left_key == right_key or left_key in right_key or right_key in left_key


def _normalize_service_name_for_match(value: Any) -> str:
    normalized = ud.normalize("NFKD", str(value or "").lower())
    without_accents = "".join(ch for ch in normalized if not ud.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", without_accents)


def _is_strategic_partner_service(value: Any) -> bool:
    normalized = _normalize_service_name_for_match(value)
    if not normalized:
        return False
    for alias in _STRATEGIC_SERVICE_ALIASES:
        normalized_alias = _normalize_service_name_for_match(alias)
        if normalized_alias and normalized_alias in normalized:
            return True
    return False


def _is_vas_section_name(section_name: str) -> bool:
    normalized = _normalize_match_text(section_name)
    return (
        "vas" in normalized
        or "valor adicionado" in normalized
        or "servicos de valor adicionado" in normalized
        or "servicos valor adicionado" in normalized
        or "sva detalhe total" in normalized
    )


def _extract_invoice_total_geral(payload: Any) -> Decimal | None:
    if isinstance(payload, dict):
        desc = _normalize_match_text(payload.get("desc", ""))
        if desc == "total geral":
            total = _decimal_from_any(
                payload.get("value")
                if "value" in payload
                else payload.get("valor")
            )
            if total is not None:
                return total
        for value in payload.values():
            if isinstance(value, (dict, list, tuple)):
                result = _extract_invoice_total_geral(value)
                if result is not None:
                    return result
    elif isinstance(payload, (list, tuple)):
        for entry in payload:
            if isinstance(entry, (dict, list, tuple)):
                result = _extract_invoice_total_geral(entry)
                if result is not None:
                    return result
    return None


def _extract_contestation_invoice_items(
    payload: Any,
    *,
    section_name: str = "",
) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        candidate_name = str(
            payload.get("desc")
            or payload.get("name")
            or payload.get("service_name")
            or payload.get("item_name")
            or payload.get("itemName")
            or payload.get("servico")
            or ""
        ).strip()
        candidate_amount = _first_decimal_from_mapping(
            payload,
            "valor_final",
            "valor",
            "price",
            "amount",
            "value",
            "valor_bruto",
            "claimedAmount",
            "validatedAmount",
        )
        if candidate_name and candidate_amount is not None and candidate_amount > 0:
            found.append(
                {
                    "name": candidate_name,
                    "amount": _money(candidate_amount),
                    "is_vas": _is_vas_section_name(section_name),
                    "section": section_name,
                    "classe": str(payload.get("classe", "")).strip().lower(),
                    "estrategico": bool(payload.get("estrategico")),
                    "verb": str(payload.get("verb", "")).strip().lower(),
                }
            )
        for key, value in payload.items():
            next_section = section_name
            if isinstance(key, str) and _is_vas_section_name(key):
                next_section = key
            if isinstance(value, (dict, list, tuple)):
                found.extend(
                    _extract_contestation_invoice_items(
                        value,
                        section_name=next_section,
                    )
                )
        return found
    if isinstance(payload, (list, tuple)):
        for item in payload:
            if isinstance(item, (dict, list, tuple)):
                found.extend(
                    _extract_contestation_invoice_items(
                        item,
                        section_name=section_name,
                    )
                )
    return found


def _has_langfuse_credentials() -> bool:
    return bool(
        os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
        and os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    )


def _start_guardrail_observation(
    *,
    name: str,
    input: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Any:
    if not _has_langfuse_credentials():
        return nullcontext(None)
    try:
        from langfuse import get_client

        return get_client().start_as_current_observation(
            name=name,
            as_type="span",
            input=input,
            metadata=metadata,
        )
    except Exception:
        logger.debug(
            "langfuse.contestation_guardrail_start_failed name=%s",
            name,
            exc_info=True,
        )
        return nullcontext(None)


def _summarize_requested_items(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    summary: list[dict[str, str]] = []
    for item in items:
        summary.append(
            {
                "item_name": str(item.get("item_name", "") or "").strip(),
                "claimed_amount": _normalize_number_text(
                    item.get("claimed_amount", "0")
                ),
                "validated_amount": _normalize_number_text(
                    item.get("validated_amount", "0")
                ),
            }
        )
    return summary


def _validation_reason(validation_log: list[dict[str, Any]]) -> str:
    for entry in validation_log:
        reason = entry.get("erro")
        if reason:
            return str(reason).strip()
    return ""


def _emit_contestation_validation_block_span(
    *,
    items: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    validation_log: list[dict[str, Any]],
    validation_error: str,
) -> None:
    reason = _validation_reason(validation_log)
    approved_count = sum(
        1 for entry in validation_log if entry.get("status") == "aprovado"
    )
    rejected_count = sum(
        1 for entry in validation_log if entry.get("status") == "reprovado"
    )
    try:
        with _start_guardrail_observation(
            name=f"guardrail.{_GUARDRAIL_CODE}.blocked",
            input={
                "items_count": len(items),
                "items": _summarize_requested_items(items),
                "invoice_candidates_count": len(candidates),
            },
            metadata={
                "mechanism": "guardrail_action_validation",
                "code": _GUARDRAIL_CODE,
                "action": _GUARDRAIL_ACTION,
                "reason": reason,
            },
        ) as obs:
            if obs is None:
                return
            obs.update(
                level="WARNING",
                output={
                    "blocked": True,
                    "error": validation_error,
                    "items_validated_count": len(validation_log),
                    "items_approved_count": approved_count,
                    "items_rejected_count": rejected_count,
                    "validation_log": validation_log,
                    "code": _GUARDRAIL_CODE,
                },
            )
    except Exception:
        logger.debug(
            "langfuse.contestation_guardrail_update_failed code=%s",
            _GUARDRAIL_CODE,
            exc_info=True,
        )


def validate_contestation_items(
    items: list[dict[str, Any]],
    invoice_payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    candidates = _extract_contestation_invoice_items(invoice_payload)
    validation_log: list[dict[str, Any]] = []

    with _start_guardrail_observation(
        name=f"guardrail.{_GUARDRAIL_CODE}.evaluated",
        input={
            "items_count": len(items),
            "items": _summarize_requested_items(items),
            "invoice_candidates_count": len(candidates),
        },
        metadata={
            "mechanism": "guardrail_action_validation",
            "code": _GUARDRAIL_CODE,
            "action": _GUARDRAIL_ACTION,
        },
    ) as obs:

        def _safe_update(**kwargs: Any) -> None:
            if obs is None:
                return
            try:
                obs.update(**kwargs)
            except Exception:
                logger.debug(
                    "langfuse.contestation_guardrail_update_failed code=%s",
                    _GUARDRAIL_CODE,
                    exc_info=True,
                )

        first_error: str | None = None

        def _record_failure(
            item_log: dict[str, Any],
            erro: str,
            message: str,
        ) -> None:
            nonlocal first_error
            item_log["status"] = "reprovado"
            item_log["erro"] = erro
            validation_log.append(item_log)
            if first_error is None:
                first_error = message

        for item in items:
            claimed = Decimal(_normalize_number_text(item.get("claimed_amount", "0")))
            validated = Decimal(
                _normalize_number_text(item.get("validated_amount", "0"))
            )
            item_name = str(item.get("item_name", "")).strip()
            if not item_name:
                continue
            item_log: dict[str, Any] = {
                "item_name": item_name,
                "item_na_fatura": False,
                "item_confirmado": False,
                "secao_vas": False,
                "valor_item_fatura": "",
                "valor_ajuste_solicitado": _normalize_number_text(
                    format(validated, "f")
                ),
                "valor_ajuste_valido": False,
                "vas_estrategico": False,
                "status": "em_validacao",
            }
            matched_candidate = next(
                (
                    candidate
                    for candidate in candidates
                    if _is_same_plan_name(candidate.get("name", ""), item_name)
                ),
                None,
            )
            if matched_candidate is None:
                _record_failure(
                    item_log,
                    "item_nao_encontrado_na_fatura",
                    f"Item '{item_name}' nao encontrado no json da fatura.",
                )
                continue
            item_log["item_na_fatura"] = True
            item_log["item_confirmado"] = True

            classe = str(matched_candidate.get("classe", "")).strip().lower()
            is_strategic = (
                classe == "estrategico"
                or bool(matched_candidate.get("estrategico"))
                or _is_strategic_partner_service(item_name)
            )
            is_vas_avulso = classe == "avulso" or (
                not classe
                and not is_strategic
                and bool(matched_candidate.get("is_vas"))
            )
            if not (is_vas_avulso or is_strategic):
                _record_failure(
                    item_log,
                    "item_fora_secao_vas",
                    f"Item '{item_name}' nao e do tipo VAS no json da fatura.",
                )
                continue
            item_log["secao_vas"] = True

            item_amount = matched_candidate.get("amount")
            if not isinstance(item_amount, Decimal) or item_amount <= 0:
                _record_failure(
                    item_log,
                    "valor_item_invalido_na_fatura",
                    f"Nao foi possivel validar o valor do item '{item_name}' na fatura.",
                )
                continue
            item_log["valor_item_fatura"] = _normalize_number_text(
                format(item_amount, "f")
            )

            if is_strategic:
                item_log["vas_estrategico"] = True
                _record_failure(
                    item_log,
                    "vas_estrategico_nao_permitido",
                    f"Item '{item_name}' identificado como VAS estrategico e nao pode ser ajustado.",
                )
                continue

            if claimed <= 0:
                claimed = item_amount
            if validated <= 0:
                validated = claimed
            if validated > item_amount:
                _record_failure(
                    item_log,
                    "valor_ajuste_maior_que_item",
                    f"Valor de ajuste do item '{item_name}' excede o valor cobrado na fatura.",
                )
                continue
            item_log["valor_ajuste_solicitado"] = _normalize_number_text(
                format(validated, "f")
            )
            item_log["valor_ajuste_valido"] = True
            item_log["status"] = "aprovado"
            validation_log.append(item_log)
            item["claimed_amount"] = _normalize_number_text(format(claimed, "f"))
            item["validated_amount"] = _normalize_number_text(format(validated, "f"))

        invoice_total = _extract_invoice_total_geral(invoice_payload)
        if invoice_total is not None and invoice_total > 0:
            total_ajustes = sum(
                (
                    Decimal(
                        _normalize_number_text(entry.get("valor_ajuste_solicitado", "0"))
                    )
                    for entry in validation_log
                    if entry.get("status") == "aprovado"
                ),
                Decimal("0"),
            )
            if total_ajustes > invoice_total:
                total_log: dict[str, Any] = {
                    "item_name": "<total_ajustes>",
                    "status": "reprovado",
                    "erro": "total_ajustes_excede_fatura",
                    "valor_total_ajustes": _normalize_number_text(
                        format(_money(total_ajustes), "f")
                    ),
                    "valor_total_fatura": _normalize_number_text(
                        format(_money(invoice_total), "f")
                    ),
                }
                validation_log.append(total_log)
                if first_error is None:
                    first_error = (
                        "Valor total de ajustes ("
                        f"{total_log['valor_total_ajustes']}) excede o "
                        f"valor total da fatura ({total_log['valor_total_fatura']})."
                    )

        approved_count = sum(
            1 for entry in validation_log if entry.get("status") == "aprovado"
        )
        rejected_count = sum(
            1 for entry in validation_log if entry.get("status") == "reprovado"
        )

        if first_error is not None:
            _emit_contestation_validation_block_span(
                items=items,
                candidates=candidates,
                validation_log=validation_log,
                validation_error=first_error,
            )
            _safe_update(
                level="WARNING",
                output={
                    "approved": False,
                    "items_count": len(items),
                    "items_validated_count": len(validation_log),
                    "items_approved_count": approved_count,
                    "items_rejected_count": rejected_count,
                    "validation_log": validation_log,
                    "error": first_error,
                    "reason": _validation_reason(validation_log),
                },
            )
            return items, validation_log, first_error

        _safe_update(
            output={
                "approved": True,
                "items_count": len(items),
                "items_validated_count": len(validation_log),
                "items_approved_count": approved_count,
                "items_rejected_count": rejected_count,
                "validation_log": validation_log,
            },
        )
        return items, validation_log, None
