# RAG Solicitado pelo Domínio

> Feature do `agent_framework_oci` — guia em Português (PT-BR).

**Implementação principal:** `runtime/agent_runtime.py`

---

### 1. O que é

Permite que uma tool ou workflow declare que a resposta precisa consultar conhecimento externo, mesmo quando já existe resultado MCP.

### 2. Problema que resolve

Em agentes de produção, não é suficiente pedir ao LLM que “faça a coisa certa”. Esta feature move uma responsabilidade específica para uma camada controlada do framework, reduzindo comportamento imprevisível e código duplicado nos agentes de domínio.

### 3. Fluxo simplificado

```text
Tool/Workflow
   ↓
requires_rag=true
   ↓
rag_query / rag_queries
   ↓
RagService do framework
   ↓
Retrieval Guardrails
   ↓
LLM/resposta
```

### 4. Como funciona internamente

Normalmente o framework pode pular RAG quando MCP já trouxe informação suficiente (`SKIP_RAG_WHEN_MCP_SUFFICIENT`). Esta feature permite que o domínio substitua essa decisão para um caso específico. O resultado pode declarar `requires_rag`, `rag_query` ou `rag_queries`; o runtime usa essas queries como override e executa o `RagService`.

O domínio informa **o que precisa saber**. Ele não implementa cliente de vetor, retriever ou prompt RAG paralelo.

### 5. Como ativar/configurar

A ativação exata depende do template/agente. Verifique o arquivo de settings, YAMLs de configuração e o template usado pelo serviço. Nem toda feature precisa de uma flag global: algumas são ativadas pelo contrato retornado por uma tool/workflow.

### 6. Exemplo

```json
{
  "requires_rag": true,
  "rag_queries": [
    "Como cancelar YouTube Premium?",
    "Como cancelar Aya Books?"
  ]
}
```

Configurações relacionadas incluem `RAG_TOP_K` e `SKIP_RAG_WHEN_MCP_SUFFICIENT`.

### 7. Telemetria e observabilidade

Quando a feature participa de uma execução de agente, preserve `request_id`, `trace_id`, `session_id`, `agent_id`, `message_id` e demais chaves de correlação no estado/eventos. Isso permite acompanhar a decisão no Langfuse/Observer sem colocar lógica de observabilidade dentro do domínio.

### 8. Como testar

1. Crie um teste unitário do comportamento principal.
2. Crie um teste de integração do runtime quando houver estado entre turns.
3. Verifique o caso feliz e pelo menos um caso de falha/negação.
4. Confirme que não há side effects duplicados em retry/replay quando a feature toca transações.
5. Em produção, valide também telemetria e correlação de IDs.

### 9. Erros comuns

- Declarar RAG para fatos transacionais já resolvidos pela API pode aumentar custo e latência.
- Query genérica demais reduz relevância.
- Nunca confie no retrieval sem `Retrieval Guardrails` quando o dado influencia resposta crítica.

### 10. Relação com outras features

Esta feature deve ser usada junto das demais capacidades horizontais do framework, em vez de criar uma implementação paralela no agente de domínio. Em fluxos transacionais, considere especialmente **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery** e **Guardrails**.

### 11. Referências no repositório

- `libs/agent_framework/src/agent_framework/runtime/agent_runtime.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
