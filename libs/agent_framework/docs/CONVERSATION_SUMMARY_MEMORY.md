# ConversationSummaryMemory

Este módulo adiciona compressão de contexto conversacional ao framework sem substituir a memória bruta existente.

## Objetivo

O framework passa a trabalhar com dois níveis de memória:

1. **Histórico bruto**: mensagens completas persistidas por `ConversationMemory`.
2. **Resumo incremental**: contexto antigo compactado por `ConversationSummaryMemory`.

O prompt final do agente pode receber:

```text
Resumo da conversa até agora:
{summary}

Últimas mensagens completas da conversa:
{recent_messages}

Mensagem do usuário:
{current_user_message}
```

## Configuração

```env
ENABLE_CONVERSATION_SUMMARY_MEMORY=true
MEMORY_CONTEXT_STRATEGY=summary
MEMORY_HISTORY_LIMIT=80
MEMORY_RECENT_MESSAGES_LIMIT=8
MEMORY_SUMMARY_TRIGGER_MESSAGES=20
MEMORY_MAX_SUMMARY_CHARS=6000
MEMORY_SUMMARY_USE_LLM=true
MEMORY_INJECT_RECENT_MESSAGES=true
MEMORY_INJECT_SUMMARY=true
```

Estratégias disponíveis:

- `none`: não injeta memória conversacional no prompt.
- `window`: injeta apenas as últimas mensagens.
- `summary`: mantém resumo acumulado das mensagens antigas e últimas mensagens completas.

## Pontos implementados

Arquivos adicionados:

```text
src/agent_framework/memory/summary_memory.py
src/agent_framework/memory/summary_store.py
```

Arquivos alterados:

```text
src/agent_framework/memory/__init__.py
src/agent_framework/config/settings.py
src/agent_framework/runtime/agent_runtime.py
src/agent_framework/persistence/sqlite_store.py
src/agent_framework/persistence/oracle_store.py
```

## Como usar no agente

Antes de chamar `build_messages()`, prepare a memória:

```python
await self.prepare_memory_context(state)

messages = self.build_messages(
    state,
    system_prompt=system_prompt,
    user_text=state.get("sanitized_input"),
)
```

O método `prepare_memory_context()` salva o resultado em:

```python
state["memory_context"]
state["memory_context_metadata"]
```

O método `build_messages()` injeta automaticamente esse contexto quando ele existe.

## Eventos de observabilidade

O runtime emite eventos IC quando a memória é carregada ou comprimida:

```text
IC.MEMORY_CONTEXT_LOADED
IC.MEMORY_COMPRESSION_TRIGGERED
IC.MEMORY_SUMMARY_UPDATED
```

## Persistência

SQLite:

```text
agent_memory_summaries
```

Oracle:

```text
<ADB_TABLE_PREFIX>_MEMORY_SUMMARY
```

MongoDB:

```text
memory_summaries
```

## Observação importante

`ConversationSummaryMemory` não é o mesmo que `Checkpoint Compaction`.

- Checkpoint compaction reduz checkpoints técnicos do LangGraph.
- ConversationSummaryMemory reduz o contexto semântico da conversa para o LLM.
