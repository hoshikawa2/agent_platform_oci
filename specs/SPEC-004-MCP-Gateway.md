# SPEC-004 — MCP Gateway

## Escopo

O MCP Gateway centraliza catálogo, autorização, roteamento, execução, cache, timeout, retry, observabilidade e resposta padronizada de tools MCP.

## Endpoints

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/health` | Health check. |
| `GET` | `/ready` | Readiness check. |
| `GET` | `/v1/tools` | Catálogo de tools. |
| `GET` | `/v1/tools/{tool_name}` | Detalhe da tool. |
| `POST` | `/v1/tools/{tool_name}/invoke` | Execução de tool. |
| `GET` | `/v1/servers` | Lista MCP servers. |

## ToolInvocation

```json
{
  "tenant_id": "default",
  "agent_id": "telecom_contas",
  "tool_name": "consultar_fatura",
  "arguments": {
    "msisdn": "11999999999",
    "invoice_id": "3000131180",
    "session_id": "default:telecom_contas:session-001"
  },
  "business_context": {
    "customer_key": "11999999999",
    "contract_key": "3000131180",
    "session_key": "session-001"
  },
  "metadata": {
    "request_id": "req-001",
    "trace_id": "trace-001"
  }
}
```

## ToolResult

```json
{
  "tool_name": "consultar_fatura",
  "ok": true,
  "data": {
    "invoice_id": "3000131180",
    "valor_total": 249.90,
    "vencimento": "2026-06-10",
    "status": "ABERTA"
  },
  "cache": {
    "hit": false,
    "ttl_seconds": 300
  },
  "latency_ms": 140,
  "metadata": {
    "server": "telecom"
  }
}
```

## mcp_servers.yaml

```yaml
servers:
  telecom:
    transport: http
    url: http://telecom-mcp:8001/mcp
    enabled: true
    timeout_seconds: 30

  retail:
    transport: http
    url: http://retail-mcp:8002/mcp
    enabled: true
    timeout_seconds: 30
```

## tools.yaml

```yaml
tools:
  consultar_fatura:
    server: telecom
    enabled: true
    idempotent: true
    cache_ttl_seconds: 300
    allowed_agents:
      - telecom_contas
    required_business_keys:
      - customer_key
      - contract_key

  solicitar_devolucao:
    server: retail
    enabled: true
    idempotent: false
    requires_confirmation: true
    allowed_agents:
      - retail_orders
```

## mcp_parameter_mapping.yaml

```yaml
tools:
  consultar_fatura:
    map:
      customer_key: msisdn
      contract_key: invoice_id
      interaction_key: ura_call_id
      session_key: session_id
```

## Autorização

```yaml
authorization:
  default_policy: deny
  agents:
    telecom_contas:
      allowed_tools:
        - consultar_fatura
        - consultar_pagamentos
        - consultar_plano
```

## Cache

| Regra | Valor |
|---|---|
| Chave | `tenant_id:agent_id:tool_name:hash(arguments)` |
| Aplicação | Apenas tools idempotentes |
| Bypass | `metadata.cache_bypass=true` |
| TTL | `cache_ttl_seconds` |
| Escrita | Não cachear operações mutáveis |

## Retry e Timeout

```yaml
execution:
  default_timeout_seconds: 30
  retry:
    enabled: true
    max_attempts: 2
    backoff_ms: 250
  circuit_breaker:
    enabled: true
    failure_threshold: 5
    recovery_seconds: 60
```

## Eventos

| Evento | Descrição |
|---|---|
| `mcp.tool.requested` | Tool requisitada. |
| `mcp.tool.authorized` | Autorização aprovada. |
| `mcp.tool.denied` | Autorização negada. |
| `mcp.tool.started` | Execução iniciada. |
| `mcp.tool.completed` | Execução concluída. |
| `mcp.tool.failed` | Execução falhou. |
| `mcp.cache.hit` | Cache hit. |
| `mcp.cache.miss` | Cache miss. |

## Métricas

| Métrica | Dimensões |
|---|---|
| `mcp_tool_calls_total` | tool, server, tenant, agent, status |
| `mcp_tool_latency_ms` | tool, server |
| `mcp_tool_errors_total` | tool, server, error_type |
| `mcp_cache_hits_total` | tool |
| `mcp_cache_misses_total` | tool |

## Segurança

- Tools são negadas por padrão.
- Argumentos sensíveis são mascarados.
- Tools mutáveis exigem confirmação quando configurado.
- MCP servers não recebem payload bruto de canal.
- Credenciais de backend são mantidas nos MCP servers ou secret store.


## Requisitos Não Funcionais

| Categoria | Requisito |
|---|---|
| Disponibilidade | Componentes deployáveis expõem `/health` e `/ready`. |
| Escalabilidade | Apps stateless escalam horizontalmente. Estado conversacional fica em repositórios externos. |
| Segurança | Segredos são fornecidos por secret store ou Kubernetes Secrets. |
| Observabilidade | Logs, métricas e traces usam correlação por request_id, trace_id, session_id, tenant_id e agent_id. |
| Auditabilidade | Decisões de rota, guardrail, judge, MCP e LLM são rastreáveis. |
| Portabilidade | Execução suportada em local, Docker Compose e Kubernetes/OKE. |
| Configuração | Comportamento variável é controlado por `.env` e YAML versionado. |


## Critérios de Aceite

- [ ] Catálogo de tools retorna tools habilitadas.
- [ ] ToolInvocation é validado antes da execução.
- [ ] Autorização por agente é aplicada.
- [ ] Parâmetros são derivados do BusinessContext.
- [ ] Cache só é aplicado a tools idempotentes.
- [ ] Timeout/retry/circuit breaker são configuráveis.
- [ ] Eventos e métricas são emitidos.
- [ ] Falhas retornam ToolResult padronizado.
- [ ] MCP servers são substituíveis por configuração.
- [ ] Tools críticas possuem testes de contrato.


## Glossário

| Termo | Definição |
|---|---|
| Agent Platform | Plataforma composta por runtime, gateways, evaluator, templates, contratos e componentes operacionais. |
| Agent Framework | Biblioteca/core reutilizável com contratos, guardrails, judges, memória, telemetria, providers e utilitários. |
| Agent Runtime | Motor de execução de agentes baseado em LangGraph, estado, sessão, memória, checkpoints, roteamento e ciclo de vida. |
| Agent Gateway | Aplicação deployável de entrada, roteamento e orquestração entre backends/agentes. |
| Channel Gateway | Aplicação ou módulo de normalização de payloads de canais para GatewayRequest. |
| AI Gateway | Aplicação de governança, roteamento e abstração de chamadas LLM/embedding. |
| MCP Gateway | Aplicação de governança e roteamento de tools MCP. |
| Evaluator | Camada de avaliação online/offline, regressão e certificação. |
| Business Context | Conjunto de chaves canônicas de negócio: customer_key, contract_key, interaction_key, account_key, resource_key e session_key. |
