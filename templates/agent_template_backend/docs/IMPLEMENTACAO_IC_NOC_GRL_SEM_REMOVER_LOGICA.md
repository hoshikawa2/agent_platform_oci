# Implementação IC/NOC/GRL preservando lógica existente

Esta versão mantém a lógica original dos agentes do `agent_template_backend` e adiciona observabilidade corporativa.

## IC adicionados nos agentes

Cada agente agora emite eventos de negócio sem alterar a resposta final:

- `IC.BILLING_AGENT_STARTED` / `IC.BILLING_AGENT_COMPLETED`
- `IC.ORDERS_AGENT_STARTED` / `IC.ORDERS_AGENT_COMPLETED`
- `IC.PRODUCT_AGENT_STARTED` / `IC.PRODUCT_AGENT_COMPLETED`
- `IC.SUPPORT_AGENT_STARTED` / `IC.SUPPORT_AGENT_COMPLETED`
- `IC.<AGENT>_MCP_CONTEXT_COLLECTED` quando houver dados MCP
- `IC.<AGENT>_RAG_CONTEXT_RETRIEVED` quando RAG estiver habilitado

O mixin `AgentRuntimeMixin` também emite:

- `IC.MCP_TOOL_CALLED` antes da chamada MCP
- `IC.TOOL_CALLED` após a chamada MCP

## NOC

O workflow já emite eventos operacionais principais:

- `NOC.001` no início da execução
- `NOC.005` em exceção fatal
- `NOC.006` na persistência/finalização

## GRL

O backend agora também exemplifica emissão GRL no workflow:

- `GRL.001` início do pipeline de guardrails
- `GRL.002` decisão allow
- `GRL.004` decisão block
- `GRL.009` decisão final agregada

Quando `OutputSupervisor` está habilitado, ele continua sendo o principal mecanismo corporativo de supervisão de saída.

## Garantia

A lógica original dos agentes não foi substituída por stubs. As chamadas LLM, MCP, RAG, cache e os retornos originais foram preservados.
