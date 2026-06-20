# Backends atualizados para ConversationSummaryMemory

Esta versão dos backends foi compatibilizada com a versão do framework que adiciona `ConversationSummaryMemory`.

## O que mudou

- `app/main.py` agora inicializa `create_conversation_summary_memory(...)` junto com `create_memory(...)`.
- `AgentWorkflow` recebe `summary_memory` e repassa para os agentes.
- Os agentes não montam mais prompts manuais para o LLM; agora usam `build_messages()` do framework.
- Antes da chamada ao LLM, os agentes executam `await self.prepare_memory_context(state)`.
- Quando habilitado por `.env`, o prompt passa a receber:
  - resumo acumulado da conversa;
  - últimas mensagens completas;
  - mensagem atual;
  - BusinessContext;
  - MCP results;
  - RAG context e metadata.

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

## Backends alterados

- `backoffice_convertido_framework`
- `agent_template_backend`
- `agent_template_backend_day_zero`

## Observação importante

Estes backends esperam que o pacote `agent_framework` instalado/conectado seja a versão com os módulos:

- `agent_framework.memory.summary_memory`
- `agent_framework.memory.summary_store`
- `AgentRuntimeMixin.prepare_memory_context()`
- `AgentRuntimeMixin.build_messages()` com injeção de memória

Use junto com o ZIP `agent_framework_conversation_summary_memory.zip`.
