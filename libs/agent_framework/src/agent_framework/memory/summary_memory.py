from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agent_framework.models.session import ChatMessage
from agent_framework.memory.message_history import ConversationMemory
from agent_framework.memory.summary_store import (
    ConversationSummaryRecord,
    ConversationSummaryStore,
    create_summary_store,
)

logger = logging.getLogger("agent_framework.memory.summary")


@dataclass(slots=True)
class MemoryContext:
    """Contexto de memória pronto para ser injetado no prompt do agente."""

    summary: str = ""
    recent_messages: list[ChatMessage] = field(default_factory=list)
    compressed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_content(self) -> bool:
        return bool(self.summary or self.recent_messages)


def _message_created_at_key(message: ChatMessage) -> str:
    value = getattr(message, "created_at", None)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value or "")


def _render_message(message: ChatMessage, max_chars: int = 1200) -> str:
    role = getattr(message, "role", "unknown") or "unknown"
    content = (getattr(message, "content", "") or "").strip()
    if len(content) > max_chars:
        content = content[:max_chars] + "... [truncado]"
    return f"{role}: {content}"


def render_recent_messages(messages: list[ChatMessage], max_chars_per_message: int = 1200) -> str:
    return "\n".join(_render_message(m, max_chars=max_chars_per_message) for m in messages if (m.content or "").strip())


class ConversationSummaryMemory:
    """Memória conversacional com compressão incremental.

    Esta classe não substitui o histórico bruto. Ela usa o ConversationMemory
    existente como fonte de verdade e mantém um resumo incremental separado por
    session_id. O prompt recebe: resumo acumulado + últimas mensagens completas.
    """

    def __init__(
        self,
        settings,
        message_history: ConversationMemory,
        summary_store: ConversationSummaryStore | None = None,
        llm=None,
        telemetry=None,
    ):
        self.settings = settings
        self.message_history = message_history
        self.summary_store = summary_store or create_summary_store(settings)
        self.llm = llm
        self.telemetry = telemetry

    @property
    def enabled(self) -> bool:
        return bool(getattr(self.settings, "ENABLE_CONVERSATION_SUMMARY_MEMORY", False))

    @property
    def strategy(self) -> str:
        return str(getattr(self.settings, "MEMORY_CONTEXT_STRATEGY", "window") or "window").lower()

    async def prepare_context(self, session_id: str, *, force: bool = False) -> MemoryContext:
        """Carrega/comprime memória e devolve o contexto pronto para prompt."""
        if not session_id or self.strategy == "none":
            return MemoryContext(metadata={"enabled": self.enabled, "strategy": self.strategy})

        history_limit = int(getattr(self.settings, "MEMORY_HISTORY_LIMIT", 80) or 80)
        recent_limit = int(getattr(self.settings, "MEMORY_RECENT_MESSAGES_LIMIT", 8) or 8)
        trigger_messages = int(getattr(self.settings, "MEMORY_SUMMARY_TRIGGER_MESSAGES", 20) or 20)

        messages = await self.message_history.list(session_id, limit=history_limit)
        recent_messages = messages[-recent_limit:] if recent_limit > 0 else []

        if self.strategy == "window" or not self.enabled:
            return MemoryContext(
                summary="",
                recent_messages=recent_messages,
                compressed=False,
                metadata={
                    "enabled": self.enabled,
                    "strategy": self.strategy,
                    "messages_loaded": len(messages),
                    "recent_messages_kept": len(recent_messages),
                },
            )

        record = await self.summary_store.get(session_id)
        should_compress = force or len(messages) >= trigger_messages
        compressed = False

        if should_compress and len(messages) > recent_limit:
            summarizable = messages[:-recent_limit] if recent_limit > 0 else messages
            if summarizable:
                summary = await self._summarize(
                    previous_summary=(record.summary if record else ""),
                    messages=summarizable,
                )
                last_message_created_at = _message_created_at_key(summarizable[-1])
                record = ConversationSummaryRecord(
                    session_id=session_id,
                    summary=summary,
                    last_message_created_at=last_message_created_at,
                    message_count_summarized=(record.message_count_summarized if record else 0) + len(summarizable),
                    metadata={
                        "strategy": self.strategy,
                        "messages_loaded": len(messages),
                        "messages_summarized_last_run": len(summarizable),
                        "recent_messages_kept": len(recent_messages),
                    },
                )
                await self.summary_store.upsert(record)
                compressed = True
                await self._emit_memory_event("IC.MEMORY_SUMMARY_UPDATED", session_id, record.metadata)

        return MemoryContext(
            summary=record.summary if record else "",
            recent_messages=recent_messages,
            compressed=compressed,
            metadata={
                "enabled": self.enabled,
                "strategy": self.strategy,
                "messages_loaded": len(messages),
                "recent_messages_kept": len(recent_messages),
                "has_summary": bool(record and record.summary),
                "compressed": compressed,
            },
        )

    async def _summarize(self, *, previous_summary: str, messages: list[ChatMessage]) -> str:
        max_summary_chars = int(getattr(self.settings, "MEMORY_MAX_SUMMARY_CHARS", 6000) or 6000)
        use_llm = bool(getattr(self.settings, "MEMORY_SUMMARY_USE_LLM", True))
        provider = str(getattr(self.settings, "LLM_PROVIDER", "mock") or "mock")

        if not self.llm or not use_llm or provider == "mock":
            return self._deterministic_summary(previous_summary=previous_summary, messages=messages, max_chars=max_summary_chars)

        transcript = render_recent_messages(messages, max_chars_per_message=1600)
        prompt = (
            "Você é uma camada de memória de um framework de agentes. "
            "Atualize o resumo da conversa de forma objetiva, preservando apenas fatos úteis para continuidade.\n\n"
            "Preserve: objetivo atual, decisões, parâmetros, identificadores de sessão/cliente quando existirem, "
            "erros, ferramentas chamadas, resultados importantes, pendências e próximos passos.\n"
            "Não invente fatos. Não inclua mensagens irrelevantes.\n\n"
            f"Resumo anterior:\n{previous_summary or '[vazio]'}\n\n"
            f"Novas mensagens a compactar:\n{transcript}\n\n"
            f"Gere um resumo atualizado em no máximo {max_summary_chars} caracteres."
        )
        try:
            summary = await self.llm.ainvoke([
                {"role": "system", "content": "Você resume memória conversacional para agentes corporativos."},
                {"role": "user", "content": prompt},
            ], max_tokens=max(256, max_summary_chars // 4), temperature=0.1, profile_name="summary_memory", component_name="summary_memory", generation_name="llm.summary_memory")
            summary = (summary or "").strip()
            if not summary:
                return self._deterministic_summary(previous_summary=previous_summary, messages=messages, max_chars=max_summary_chars)
            return summary[:max_summary_chars]
        except Exception as exc:
            logger.exception("Falha ao resumir memória com LLM; usando fallback determinístico: %s", exc)
            return self._deterministic_summary(previous_summary=previous_summary, messages=messages, max_chars=max_summary_chars)

    def _deterministic_summary(self, *, previous_summary: str, messages: list[ChatMessage], max_chars: int) -> str:
        rendered = render_recent_messages(messages, max_chars_per_message=800)
        parts = []
        if previous_summary:
            parts.append(previous_summary.strip())
        if rendered:
            parts.append("Resumo incremental determinístico das mensagens antigas:\n" + rendered)
        summary = "\n\n".join(parts).strip()
        if len(summary) > max_chars:
            summary = summary[-max_chars:]
            summary = "[continuação do resumo compactado]\n" + summary
        return summary

    async def _emit_memory_event(self, event_name: str, session_id: str, metadata: dict[str, Any]) -> None:
        if not self.telemetry:
            return
        try:
            await self.telemetry.event(event_name, {"session_id": session_id, **(metadata or {})}, kind="memory")
        except Exception:
            logger.debug("Falha não crítica ao emitir evento de memória", exc_info=True)


def create_conversation_summary_memory(settings, message_history: ConversationMemory, llm=None, telemetry=None) -> ConversationSummaryMemory:
    return ConversationSummaryMemory(
        settings=settings,
        message_history=message_history,
        summary_store=create_summary_store(settings),
        llm=llm,
        telemetry=telemetry,
    )
