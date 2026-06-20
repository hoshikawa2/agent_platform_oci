# Langfuse Internal Event Root Trace Fix

## Problema

Alguns eventos internos IC/NOC/GRL estavam aparecendo na tela **Tracing → Traces** como traces raiz separados, mesmo quando pertenciam à mesma execução REST/workflow.

Exemplo observado:

```text
Name: http.request.completed
Input: {"eventType": "NOC.006", ...}
Output: {"published": true}
```

Esse registro não representa a execução real do agente. Ele representa apenas a publicação de um evento interno via analytics, e por isso não deve aparecer como trace raiz.

## Correção

O arquivo abaixo foi ajustado:

```text
src/agent_framework/analytics/providers/langfuse.py
```

A nova regra é:

```text
1 request/workflow = 1 trace raiz
IC/NOC/GRL = observations/spans dentro do trace corrente
Eventos internos embrulhados em http.request/gateway/telemetry não criam trace raiz
```

## Regras aplicadas

O publisher agora:

1. Detecta envelopes internos como `IC.*`, `NOC.*`, `GRL.*` e `AGA.*`.
2. Suprime eventos técnicos do tipo `http.request.completed` cujo input real é um envelope interno como `NOC.006`.
3. Prioriza correlação por `ObservabilityContext`:

```text
trace_id/request_id do contexto atual
> trace_id/request_id do payload
> transaction_id/session_id apenas como fallback
```

4. Evita fallback para `langfuse.trace(...)` ou `langfuse.span(...)` para eventos internos/técnicos quando a observation correlacionada falha.
5. Mantém a flag abaixo para debug isolado:

```bash
export LANGFUSE_ALLOW_STANDALONE_INTERNAL_EVENTS=true
```

Por padrão, essa flag deve ficar desligada.

## Resultado esperado

Na tela **Tracing → Traces**, uma execução nova deve aparecer como uma linha principal, por exemplo:

```text
http.request.completed
```

ou:

```text
backoffice.process-and-stream
```

Ao abrir o trace, devem aparecer internamente:

```text
IC.BACKOFFICE_WORKFLOW_COMPLETED
NOC.006
langgraph.node.*
mcp.tool_call.*
guardrail.*
judge.*
```

O trace solto com `Input: {"eventType": "NOC.006"}` e `Output: {"published": true}` deve desaparecer.
