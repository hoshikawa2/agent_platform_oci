# RAG Solicitado pelo Domínio / Domain Requested RAG

> Feature do `agent_framework_oci` — guia bilíngue PT-BR / EN.

**Implementação principal / Main implementation:** `runtime/agent_runtime.py`

---

## Português (PT-BR)

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

---

## English (EN)

### 1. What it is

Allows a tool or workflow to declare that external knowledge retrieval is required even when an MCP result already exists.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
Tool/Workflow
   ↓
requires_rag=true
   ↓
rag_query / rag_queries
   ↓
framework RagService
   ↓
Retrieval Guardrails
   ↓
LLM/response
```

### 4. How it works internally

Normally the framework may skip RAG when MCP already provides sufficient data (`SKIP_RAG_WHEN_MCP_SUFFICIENT`). This feature lets the domain override that decision for a specific case. A result may declare `requires_rag`, `rag_query`, or `rag_queries`; the runtime uses those queries as overrides and invokes `RagService`.

The domain declares **what knowledge is needed**. It does not implement its own vector client, retriever, or parallel RAG prompt stack.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```json
{
  "requires_rag": true,
  "rag_queries": [
    "How to cancel YouTube Premium?",
    "How to cancel Aya Books?"
  ]
}
```

Related settings include `RAG_TOP_K` and `SKIP_RAG_WHEN_MCP_SUFFICIENT`.

### 7. Telemetry and observability

When the feature participates in an agent execution, preserve `request_id`, `trace_id`, `session_id`, `agent_id`, `message_id`, and other correlation keys in state/events. This makes the decision observable through Langfuse/Observer without embedding observability logic in the domain.

### 8. How to test

1. Add a unit test for the core behavior.
2. Add a runtime integration test when state spans multiple turns.
3. Test the happy path and at least one failure/rejection path.
4. Confirm retries/replays do not duplicate side effects for transactional features.
5. In production, also validate telemetry and ID correlation.

### 9. Common mistakes

- Requesting RAG for transactional facts already resolved by an API adds unnecessary cost and latency.
- Queries that are too broad reduce relevance.
- Do not trust retrieved content for critical responses without Retrieval Guardrails.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/runtime/agent_runtime.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
