from __future__ import annotations

import re
from typing import Any


def confirmation_decision(text: str) -> str | None:
    """Classifica respostas explícitas ao estado AWAITING_CONFIRMATION.

    Esta função é compartilhada pelo router (precedência antes de intent_shift)
    e pelo runtime (execução/cancelamento efetivo), garantindo que ambos
    reconheçam exatamente o mesmo conjunto de respostas.
    """
    normalized = " ".join((text or "").strip().lower().split())
    normalized = re.sub(r"[.!?]+$", "", normalized).strip()
    if normalized in {
        "sim",
        "confirmo",
        "sim, confirmo",
        "pode fazer",
        "pode prosseguir",
        "sim, desejo",
        "sim, desejo trocar",
        "sim, confirmo a devolução",
        "sim, confirmo a troca",
    }:
        return "confirm"
    if normalized in {"não", "nao", "cancelar", "cancele", "não confirmo", "nao confirmo"}:
        return "reject"
    return None


def extract_action_arguments(text: str) -> dict[str, Any]:
    """Extrai entidades explicitamente informadas em ações transacionais.

    É usada tanto pelo runtime quanto pelo probe de precedência do router. Não
    transforma a mensagem inteira em motivo: só captura valores explicitamente
    identificáveis no turno atual.
    """
    raw = text or ""
    args: dict[str, Any] = {}
    match = re.search(
        r"(?:pedido|ordem)\s*(?:n[ºo°.]?\s*)?(?:é\s*(?:o\s*)?|[:#=-]\s*)?([A-Za-z0-9_-]+)",
        raw,
        flags=re.IGNORECASE,
    )
    if match:
        args["order_id"] = match.group(1)

    reason_match = re.search(
        r"(?:porque|pois|motivo\s*[:=-]?|por\s+(?:arrependimento|defeito|erro|atraso)|me\s+arrependi(?:\s+da\s+compra)?|arrependimento)\s*(.*)",
        raw,
        flags=re.IGNORECASE,
    )
    if reason_match:
        reason = reason_match.group(1).strip(" .,:;-")
        if not reason:
            matched_phrase = reason_match.group(0).strip(" .,:;-")
            if re.search(r"me\s+arrependi|arrependimento", matched_phrase, flags=re.IGNORECASE):
                reason = "Arrependimento da compra"
        if reason:
            args["reason"] = reason
    return args
