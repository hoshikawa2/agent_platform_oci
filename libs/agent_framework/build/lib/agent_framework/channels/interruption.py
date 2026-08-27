from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class InterruptionDecision:
    action: str  # process | replay | classify
    text: str
    replay_text: str = ""
    reason: str = ""
    is_interruptible: bool = True
    terminal_status: str = ""
    heard_text: str = ""


def _idle_nudges(payload: dict[str, Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for event in payload.get("events") or []:
        if not isinstance(event, dict) or event.get("type") != "idle_nudge":
            continue
        text = str(event.get("text") or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


async def classify_processing_interruption(
    llm: Any,
    *,
    original_agent: str,
    original_client: str = "",
    supplement_client: str = "",
    profile_name: str = "processing_interruption_classifier",
) -> bool:
    """Decide se um barge-in interrompível exige regeneração da resposta.

    Fail-safe: qualquer erro, resposta vazia ou formato inesperado retorna False,
    fazendo replay da fala anterior. O domínio não conhece este classificador;
    ele usa exclusivamente o LLMProvider do framework.
    """
    if llm is None:
        return False
    prompt = (
        "Você classifica interrupções de voz durante uma resposta de atendimento. "
        "Responda somente 1 ou 0.\n"
        "1 = a fala/complemento do cliente adiciona ou altera informação relevante e "
        "a resposta do agente deve ser regenerada.\n"
        "0 = a interrupção não exige nova resposta; a fala anterior deve ser repetida.\n\n"
        f"Última fala do agente: {original_agent}\n"
        f"Última fala do cliente antes da resposta: {original_client}\n"
        f"Complemento/interrupção atual: {supplement_client}\n"
    )
    try:
        response = await llm.ainvoke(
            [{"role": "system", "content": prompt}],
            temperature=0,
            max_tokens=8,
            profile_name=profile_name,
            component_name=profile_name,
            generation_name=f"llm.{profile_name}",
        )
        raw = getattr(response, "content", response)
        text = str(raw or "").strip()
        return text.startswith("1")
    except Exception:
        return False


def evaluate_interruption(
    *,
    payload: dict[str, Any],
    message_text: str,
    session_metadata: dict[str, Any] | None,
    terminal_fallback_text: str = "",
    terminal_fallback_status: str = "erro_falha_sistema",
) -> InterruptionDecision:
    """Framework-level replay/interruption policy.

    - sessão terminal: replay da última fala/fallback, sem reabrir o workflow;
    - idle_nudge: replay da última fala real;
    - fala não interrompível: replay;
    - fala interrompível com fala anterior: classificar antes de regenerar;
    - sem contexto anterior suficiente: processar normalmente.
    """
    metadata = session_metadata or {}
    last_text = str(metadata.get("last_assistant_text") or "").strip()
    last_interruptible = bool(metadata.get("last_assistant_is_interruptible", True))

    if bool(metadata.get("conversation_closed")):
        replay_text = (
            last_text
            or str(metadata.get("terminal_replay_text") or "").strip()
            or str(terminal_fallback_text or "").strip()
        )
        terminal_status = str(metadata.get("terminal_status") or "").strip() or terminal_fallback_status
        if replay_text:
            return InterruptionDecision(
                action="replay",
                text=message_text,
                replay_text=replay_text,
                reason="post_finalize",
                is_interruptible=False,
                terminal_status=terminal_status,
            )

    if _idle_nudges(payload) and last_text:
        return InterruptionDecision(
            action="replay",
            text=message_text,
            replay_text=last_text,
            reason="idle_nudge",
            is_interruptible=last_interruptible,
        )

    interruption = payload.get("processing_interruption")
    if isinstance(interruption, dict):
        heard = str(interruption.get("heard_text") or "").strip()
        current_text = str(message_text or heard).strip()
        if not last_interruptible and last_text:
            return InterruptionDecision(
                action="replay",
                text=current_text,
                replay_text=last_text,
                reason="non_interruptible_speech",
                is_interruptible=False,
                heard_text=heard,
            )
        if last_text:
            return InterruptionDecision(
                action="classify",
                text=current_text,
                replay_text=last_text,
                reason="interruptible_speech",
                is_interruptible=True,
                heard_text=heard,
            )
        return InterruptionDecision(
            action="process",
            text=current_text,
            reason="interruptible_speech_no_history",
            is_interruptible=True,
            heard_text=heard,
        )

    return InterruptionDecision(action="process", text=message_text)


__all__ = [
    "InterruptionDecision",
    "classify_processing_interruption",
    "evaluate_interruption",
]
