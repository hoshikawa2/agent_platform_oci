"""Formatacao do `context` do agente para prompts de guardrail.

Os rails de output (OOS, AOFERTA, REVPREC, PINJ, RAGSEC, DLEX_OUT) precisam
auditar a fala do agente *com referencia* ao que o cliente pediu e ao que o
agente esta executando — sem isso, OOS classifica "Olá, como vai?" como
in-scope (a frase em si nao e off-topic) quando deveria reprovar o turno
porque o cliente perguntou algo fora de telecom.

`format_context_block` extrai o historico recente da conversa (com tool calls
e tool results) e o renderiza como string pronta para ser injetada no prompt.
SystemMessage e filtrada — o rail nao precisa do system prompt do agente.
"""
from __future__ import annotations

import json
from typing import Any


def _truncate(text: str, limit: int = 2000) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


_ROLE_BY_CLASS = {
    "HumanMessage": "user",
    "AIMessage": "assistant",
    "ToolMessage": "tool",
    "FunctionMessage": "tool",
}


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


def _tool_call_name(call: dict) -> str:
    name = call.get("name") or call.get("tool")
    if isinstance(name, str) and name:
        return name
    function = call.get("function")
    if isinstance(function, dict):
        fn_name = function.get("name")
        if isinstance(fn_name, str):
            return fn_name
    elif isinstance(function, str):
        return function
    return ""


def _format_tool_calls(tool_calls: Any) -> str:
    if not isinstance(tool_calls, list) or not tool_calls:
        return ""
    rendered: list[str] = []
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        name = _tool_call_name(call)
        if not name:
            continue
        args = call.get("args") or call.get("arguments") or {}
        if isinstance(args, str):
            args_str = args
        else:
            try:
                args_str = json.dumps(args, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                args_str = str(args)
        rendered.append(f"{name}({_truncate(args_str, 300)})")
    return "; ".join(rendered)


def _format_conversation_history(
    history: Any,
    *,
    per_message_limit: int = 2000,
    trim_trailing_assistant: bool = True,
) -> str:
    """Renderiza historico filtrando SystemMessage e expondo tool calls.

    Cada AIMessage com `tool_calls` ganha uma linha extra `[assistant->tool]`
    listando nome(args). ToolMessage aparece como `[tool] <content>`. System
    e omitida porque o rail nao precisa do prompt do agente.

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
        if cls == "SystemMessage":
            continue
        role = _ROLE_BY_CLASS.get(cls, cls.lower())
        content = _message_content_to_str(getattr(msg, "content", ""))
        if content.strip():
            lines.append(f"[{role}] {_truncate(content, per_message_limit)}")
        tool_calls = getattr(msg, "tool_calls", None)
        rendered_tools = _format_tool_calls(tool_calls)
        if rendered_tools:
            lines.append(f"[{role}->tool] {rendered_tools}")
    return "\n".join(lines)


def format_context_block(context: dict | None) -> str:
    """Renderiza o bloco de contexto padrao para rails de guardrail.

    Retorna string vazia quando nao ha historico util. Formato:

        Historico da conversa:
        [user] ...
        [assistant] ...
        [assistant->tool] buscar_informacao({...})
        [tool] ...
        [user] ...

    Builders de prompt recebem esta string ja formatada e a injetam no
    template — eles nao tocam no dict de contexto cru.
    """
    if not isinstance(context, dict) or not context:
        return ""
    history_block = _format_conversation_history(
        context.get("conversation_history"),
        trim_trailing_assistant=True,
    )
    if not history_block:
        return ""
    return f"\nHistorico da conversa:\n{history_block}\n"
