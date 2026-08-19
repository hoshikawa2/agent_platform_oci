# Domain-Requested RAG

## Objetivo

Permitir que uma tool/workflow de domínio declare que o resultado MCP **não é suficiente** para produzir a resposta final e que o agente deve recuperar conhecimento usando o `RagService` oficial do `agent_framework_oci`.

O domínio não instancia banco vetorial, embeddings, LLM ou cliente RAG. Ele apenas devolve no resultado:

```json
{
  "requires_rag": true,
  "rag_queries": [
    "Como cancelar o serviço Paramount+ no parceiro? Procedimento oficial de cancelamento."
  ]
}
```

## Fluxo

```text
Workflow/tool de domínio
        |
        | requires_rag + rag_queries
        v
AgentRuntimeMixin
        |
        +-- impede direct MCP answer
        +-- ignora SKIP_RAG_WHEN_MCP_SUFFICIENT para este resultado
        +-- usa rag_query/rag_queries como query override
        v
RagService
        v
Vector/Graph store configurado no framework
        v
LLM do agente com MCP evidence + RAG evidence
```

## Regras

1. `requires_rag=false` ou ausente mantém o comportamento padrão.
2. `SKIP_RAG_WHEN_MCP_SUFFICIENT=true` continua válido para tools normais.
3. Quando `requires_rag=true`, o framework não usa `build_direct_mcp_answer()`.
4. `rag_query` aceita uma query; `rag_queries` aceita várias queries, preservadas e deduplicadas em ordem.
5. O domínio nunca executa `RagService` diretamente.
6. Guardrails de retrieval (`RAGSEC`, `RET_REL` etc.) continuam executando normalmente sobre o contexto recuperado.

## Exemplo Contas

No fluxo VAS Estratégico, após o cliente rejeitar a explicação e pedir cancelamento, a action devolve queries específicas por parceiro. O `VasAgent` usa o `RagService` do framework para recuperar o procedimento oficial e compor a resposta.

Isso substitui o comportamento legado em que o backend Contas possuía uma busca RAG própria dentro de `vas_strategic()`.
