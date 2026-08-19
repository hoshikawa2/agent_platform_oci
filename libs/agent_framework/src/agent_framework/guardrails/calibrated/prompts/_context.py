"""Formatacao do `context` do agente para prompts de guardrail.

Os rails de output (OOS, AOFERTA, REVPREC, PINJ, RAGSEC, DLEX_OUT) precisam
auditar a fala do agente *com referencia* ao que o cliente pediu e ao que o
agente esta executando — sem isso, OOS classifica "Olá, como vai?" como
in-scope (a frase em si nao e off-topic) quando deveria reprovar o turno
porque o cliente perguntou algo fora de telecom.

`format_context_block` extrai o historico recente da conversa e o renderiza
como string pronta para ser injetada no prompt. So os turnos de fala entram:
SystemMessage, ToolMessage e as linhas de tool_call sao filtrados — o rail
julga a CONVERSA, e o resultado de tool que importa ja aparece ecoado na fala
do assistente (mante-los so duplicava o turno e gastava token do auditor).
"""
from __future__ import annotations

from typing import Any


def _truncate(text: str, limit: int = 2000) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


_ROLE_BY_CLASS = {
    "HumanMessage": "user",
    "AIMessage": "assistant",
}

# Filtradas do bloco: system nao e conversa; tool e duplicata do que o
# assistente ecoa em seguida (ver docstring do modulo).
_SKIPPED_CLASSES = frozenset({"SystemMessage", "ToolMessage", "FunctionMessage"})


def _message_content_to_str(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text") or part.get("content")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(parts)
    return str(content) if content is not None else ""


def _format_conversation_history(
    history: Any,
    *,
    per_message_limit: int = 2000,
    trim_trailing_assistant: bool = True,
) -> str:
    """Renderiza o historico so com os turnos de FALA (user/assistant).

    SystemMessage, ToolMessage e tool_calls sao filtrados (ver docstring do
    modulo): o rail julga a conversa, e o conteudo de tool ja chega ecoado na
    fala do assistente.

    `trim_trailing_assistant` remove a ultima AIMessage do final — os output
    rails recebem essa mensagem como `text` e ela ja aparece no bloco
    "Resposta:", sem trim ela duplicaria.
    """
    if not isinstance(history, list) or not history:
        return ""
    msgs = list(history)
    if trim_trailing_assistant and msgs:
        if type(msgs[-1]).__name__ == "AIMessage":
            msgs.pop()
    lines: list[str] = []
    for msg in msgs:
        cls = type(msg).__name__
        if cls in _SKIPPED_CLASSES:
            continue
        role = _ROLE_BY_CLASS.get(cls, cls.lower())
        content = _message_content_to_str(getattr(msg, "content", ""))
        if content.strip():
            lines.append(f"[{role}] {_truncate(content, per_message_limit)}")
    return "\n".join(lines)


def format_context_block(
    context: dict | None,
    *,
    trim_trailing_assistant: bool = True,
) -> str:
    """Renderiza o bloco de contexto padrao para rails de guardrail.

    `trim_trailing_assistant=False` mantem a ultima fala do agente no bloco —
    necessario para rails de INPUT que julgam a fala do cliente COMO RESPOSTA
    (ex.: COER), onde a pergunta pendente do agente e justamente o que decide
    o veredito. Para rails de OUTPUT o default (True) continua valendo: a fala
    do agente ja vem no bloco "Resposta:".

    Retorna string vazia quando nao ha historico util. Formato:

        Historico da conversa:
        [user] ...
        [assistant] ...
        [user] ...

    Builders de prompt recebem esta string ja formatada e a injetam no
    template — eles nao tocam no dict de contexto cru.
    """
    if not isinstance(context, dict) or not context:
        return ""
    history_block = _format_conversation_history(
        context.get("conversation_history"),
        trim_trailing_assistant=trim_trailing_assistant,
    )
    if not history_block:
        return ""
    return f"\nHistorico da conversa:\n{history_block}\n"
