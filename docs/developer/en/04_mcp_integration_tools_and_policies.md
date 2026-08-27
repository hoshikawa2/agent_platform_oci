
### MCP, Tools, Policies and Parameter Extraction

### How to use this manual

This is a **specialized reference manual**. It does not replace the main tutorial.

- To build an agent end to end, use [`README_en.md`](../../../README_en.md).
- Use this document when implementing, deep-diving or troubleshooting **tools, MCP Servers, mappings, read-only/transactional policies and parameter extraction**.
- Historical examples consolidated here must be interpreted against the current framework API.
- If documentation differs, the current code and root README take precedence.

### Relationship with the main tutorial

`README_en.md` introduces this capability as part of the normal development flow. This manual consolidates details previously spread across `docs/`, `Documentacao/`, release notes, validation records and specialized guides.

Its purpose is to answer **“how does this feature work in depth and how do I troubleshoot it?”** without becoming a second copy of the main tutorial.

### Scope

Tools, mcp servers, mappings, read-only/transactional policies and parameter extraction.

### Consolidated technical content

### MCP Integration, Tools, Policies and Parameter Extraction

This guide explains how agents consume business capabilities through MCP without embedding service logic in the framework.

### MCP role

MCP is the integration boundary for tools. The framework/runtime selects and prepares a tool call; the MCP layer connects that logical tool to a service. Business authorization, atomicity and backend transaction guarantees remain responsibilities of the MCP Server/service implementation.

### Registering an MCP Server

For local execution, register the server in the backend/gateway MCP configuration with its transport, endpoint, enabled flag and description. Docker/Kubernetes configurations should use the service DNS name rather than localhost.

```yaml
servers:
  crm:
    transport: http
    endpoint: http://localhost:8300/mcp
    enabled: true
    description: CRM MCP Server
```

### Registering a tool

```yaml
tools:
  consultar_cliente:
    description: Query summarized customer data.
    mcp_server: crm
    enabled: true
    args_schema:
      customer_id: string
      document_id: string
```

The tool description and parameter descriptions are part of runtime behavior. They should be precise enough for semantic selection/extraction and must not be hidden in Python hardcodes.

### Tool isolation per agent

Every agent should see only the tools it needs. Use an allowlist or agent-specific `tools.yaml`. This reduces prompt ambiguity and limits operational risk.

### Read-only versus transactional policies

Policy configuration is optional and lives with the deployable agent, not inside the shared library. A default may treat tools as read-only, while individual tools declare `operation_type: transactional`, `require_confirmation: true` and required parameters.

```yaml
defaults:
  operation_type: read_only
  require_confirmation: false

tool_policies:
  alterar_plano:
    operation_type: transactional
    require_confirmation: true
    requires: [new_plan_id]
```

If policy configuration is absent, legacy metadata in `tools.yaml` remains valid. Old tools without a policy must keep their previous behavior.

### Confirmation contract

A blocked transactional call must not reach MCP. The runtime returns policy metadata explaining why it was blocked. Confirmation must be represented by the transaction/runtime confirmation contract; a random textual field containing the word `true` is not sufficient evidence.

### LLM-based parameter extraction

Parameter extraction supports natural language and multi-turn collection. The user may provide `name=value`, a natural phrase, only the value when one parameter is unambiguously missing, or several parameters in one turn. Extraction uses the active tool/workflow schema and parameter descriptions; it must not rely on a domain-specific regex list in the framework.

Extracted values are merged into the active transaction before generic rerouting decisions. If extraction cannot determine a required value reliably, the agent asks for the missing parameter rather than inventing it.

### MCP Server implementation

A server exposes a tool catalog/schema and a call endpoint/transport. The business implementation validates the arguments, invokes the backend and returns a structured success/error result. Transactional services should implement authorization/idempotency as appropriate to the backend contract.

### Security and observability checklist

- Explicit schema and description for every tool.
- Explicit confirmation for configured side effects.
- Tool allowlist per agent.
- Sensitive-result sanitization/masking before user presentation.
- Trace/span/event for each MCP invocation.
- Configured timeouts/retries.
- Do not expose MCP Servers publicly without authentication, TLS and network controls.
- Separate read-only and transactional operations.

Recommended telemetry includes tenant, agent, session, tool, MCP server, latency, success/error and argument-key metadata without leaking sensitive values.

### Source material consolidated

- `Documentacao/Manual_Integracao_MCP_Servers_Agent_Framework.docx`
- `Documentacao/README_TOOL_POLICIES.md`
- `Documentacao/RELEASE_NOTES_TOOL_POLICIES.md`
- `Documentacao/RELEASE_NOTES_MCP_PARAMETER_EXTRACTION_FIX.md`
- `Documentacao/README_MCP.md`

### Detailed normative and implementation reference

The sections below preserve the detailed English project specifications and implementation guides relevant to this capability. They are included here so a developer does not need to reconstruct the behavior from separate documents.

### MCP discovery and catalog details

> Consolidated from `docs/MCP_GATEWAY_DISCOVERY.md`.

### Goal

This evolution allows the MCP Gateway to discover tools from registered MCP Servers by reading a manifest or catalog endpoint.

The framework still points to a single MCP Gateway:

```env
MCP_GATEWAY_ENABLED=true
MCP_GATEWAY_URL=http://localhost:8300
MCP_GATEWAY_TIMEOUT_SECONDS=60
```

The MCP Gateway can point to many MCP Servers:

```text
Agent Framework
  -> MCP Gateway
     -> telecom_mcp_server
     -> retail_mcp_server
     -> nf_items_mcp_server
     -> any other MCP Server
```

### What is automatic

After a server is registered in `apps/mcp_gateway/config/mcp_gateway.yaml` with `discover: true`, the gateway can:

- call its manifest/catalog endpoint;
- normalize the returned tool list;
- publish the tools in `GET /v1/tools`;
- execute the discovered tool through `POST /v1/tools/{tool_name}/invoke`.

### What is still explicit

The gateway does not scan the network or GitHub by itself. You still register the MCP Server endpoint in YAML.

Example:

```yaml
servers:
  nf_items:
    enabled: true
    discover: true
    protocol: legacy_http
    transport: http
    url: http://localhost:8400/mcp
    catalog_endpoint: /tools
    invoke_endpoint: /tools/call
    timeout_seconds: 30
```

If `catalog_endpoint` is omitted, the gateway tries:

```text
/.well-known/mcp-server.json
/manifest
/mcp/tools
/tools/list
/tools
/v1/tools
```

### Expected manifest/catalog formats

The gateway accepts common shapes:

```json
{
  "server_id": "nf_items",
  "tools": [
    {
      "name": "buscar_notas_por_criterios",
      "description": "Search invoice items by criteria.",
      "input_schema": {
        "cliente": "string",
        "estado": "string",
        "preco": "number",
        "ean": "string",
        "margem": "number"
      }
    }
  ]
}
```

It also accepts:

```json
{"tools": [...]}
```

```json
{"data": {"tools": [...]}}
```

```json
{"capabilities": {"tools": [...]}}
```

### New endpoints

### List discovery servers

```bash
curl http://localhost:8300/v1/discovery/servers | jq
```

### Force catalog sync

```bash
curl -X POST http://localhost:8300/v1/discovery/sync | jq
```

### List merged static + discovered tools

```bash
curl http://localhost:8300/v1/tools | jq
```

### Precedence rule

Static tools configured under `tools:` override discovered tools with the same name. This allows operations teams to override timeout, cache, allowed agents, required business keys, and endpoint behavior safely.

### Plugging a new MCP Server

1. Start the MCP Server.
2. Confirm that it exposes a catalog or manifest endpoint.
3. Add it under `servers:` in `mcp_gateway.yaml` with `discover: true`.
4. Restart the MCP Gateway or call `POST /v1/discovery/sync`.
5. Confirm the tool appears in `GET /v1/tools`.
6. Invoke the tool through the gateway.

### Example invocation

```bash
curl -s -X POST http://localhost:8300/v1/tools/buscar_notas_por_criterios/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "default",
    "agent_id": "telecom_contas",
    "channel": "web",
    "tool_name": "buscar_notas_por_criterios",
    "arguments": {
      "cliente": "CLIENTE-001",
      "estado": "SP",
      "preco": 100.0,
      "ean": "7890000000000",
      "margem": 0.05
    },
    "business_context": {
      "session_key": "session-001"
    }
  }' | jq
```

### MCP Gateway specification

> Consolidated from `specs/SPEC-004-MCP-Gateway.md`.

### Escopo

O MCP Gateway centraliza catálogo, autorização, roteamento, execução, cache, timeout, retry, observabilidade e resposta padronizada de tools MCP.

### Endpoints

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/health` | Health check. |
| `GET` | `/ready` | Readiness check. |
| `GET` | `/v1/tools` | Catálogo de tools. |
| `GET` | `/v1/tools/{tool_name}` | Detalhe da tool. |
| `POST` | `/v1/tools/{tool_name}/invoke` | Execução de tool. |
| `GET` | `/v1/servers` | Lista MCP servers. |

### ToolInvocation

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

### ToolResult

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

### mcp_servers.yaml

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

### tools.yaml

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

### mcp_parameter_mapping.yaml

```yaml
tools:
  consultar_fatura:
    map:
      customer_key: msisdn
      contract_key: invoice_id
      interaction_key: ura_call_id
      session_key: session_id
```

### Autorização

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

### Cache

| Regra | Valor |
|---|---|
| Chave | `tenant_id:agent_id:tool_name:hash(arguments)` |
| Aplicação | Apenas tools idempotentes |
| Bypass | `metadata.cache_bypass=true` |
| TTL | `cache_ttl_seconds` |
| Escrita | Não cachear operações mutáveis |

### Retry e Timeout

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

### Eventos

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

### Métricas

| Métrica | Dimensões |
|---|---|
| `mcp_tool_calls_total` | tool, server, tenant, agent, status |
| `mcp_tool_latency_ms` | tool, server |
| `mcp_tool_errors_total` | tool, server, error_type |
| `mcp_cache_hits_total` | tool |
| `mcp_cache_misses_total` | tool |

### Segurança

- Tools são negadas por padrão.
- Argumentos sensíveis são mascarados.
- Tools mutáveis exigem confirmação quando configurado.
- MCP servers não recebem payload bruto de canal.
- Credenciais de backend são mantidas nos MCP servers ou secret store.


### Requisitos Não Funcionais

| Categoria | Requisito |
|---|---|
| Disponibilidade | Componentes deployáveis expõem `/health` e `/ready`. |
| Escalabilidade | Apps stateless escalam horizontalmente. Estado conversacional fica em repositórios externos. |
| Segurança | Segredos são fornecidos por secret store ou Kubernetes Secrets. |
| Observabilidade | Logs, métricas e traces usam correlação por request_id, trace_id, session_id, tenant_id e agent_id. |
| Auditabilidade | Decisões de rota, guardrail, judge, MCP e LLM são rastreáveis. |
| Portabilidade | Execução suportada em local, Docker Compose e Kubernetes/OKE. |
| Configuração | Comportamento variável é controlado por `.env` e YAML versionado. |


### Critérios de Aceite

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


### Glossário

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

### Política mínima de operação

Antes de encaminhar uma tool, o runtime deve aplicar a política opcional do backend em `config/tool_policies.yaml`. Os tipos canônicos são `read_only` e `transactional`; esta última pode exigir confirmação booleana explícita e campos obrigatórios. A ausência do arquivo não é erro e preserva os campos legados de `tools.yaml`. A política conversacional não substitui autenticação, autorização, idempotência nem atomicidade no MCP Server.

### Agent tool integration requirements

> Consolidated from `specs/SPEC-010-Agent-Development.md`.

### Escopo

Esta SPEC define o padrão para criação de agentes usando templates, configuração YAML, BusinessContext, MCP, guardrails, judges, RAG, memória, observabilidade e evals.

### Estrutura do Template

```text
templates/agent_template_backend/
├── app/
│   ├── main.py
│   ├── state.py
│   ├── workflows/
│   │   └── agent_graph.py
│   ├── agents/
│   │   ├── runtime.py
│   │   └── domain_agent.py
│   └── examples/
├── config/
│   ├── agents.yaml
│   ├── routing.yaml
│   ├── tools.yaml
│   ├── mcp_servers.yaml
│   ├── mcp_parameter_mapping.yaml
│   ├── identity.yaml
│   ├── guardrails.yaml
│   ├── judges.yaml
│   ├── prompt_policy.yaml
│   └── agents/<agent_id>/
├── Dockerfile
├── requirements.txt
└── .env.example
```

### Responsabilidades do Framework

- LangGraph;
- memória;
- checkpoint;
- sessão;
- router;
- supervisor;
- guardrails;
- judges;
- telemetry;
- MCP integration;
- RAG genérico;
- cache;
- providers LLM;
- event bus.

### Responsabilidades do Agente

- prompts de domínio;
- regras de negócio;
- schemas específicos;
- decisão de uso de evidências;
- tratamento de campos obrigatórios;
- mensagens de domínio;
- ICs de jornada;
- datasets de eval específicos.

### Registro do Agente

```yaml
agents:
  financeiro_agent:
    enabled: true
    description: "Agente financeiro"
    profile: financeiro_agent
    rag_namespace: financeiro
    allowed_tools:
      - consultar_fatura
      - consultar_pagamentos
```

### Roteamento

```yaml
intents:
  financeiro_consulta_fatura:
    route: financeiro_agent
    keywords:
      - fatura
      - boleto
      - cobrança
    mcp_tools:
      - consultar_fatura
```

### Tool Mapping

```yaml
tools:
  consultar_fatura:
    map:
      customer_key: msisdn
      contract_key: invoice_id
      interaction_key: ura_call_id
      session_key: session_id
```

### Classe de Agente

```python
class FinanceiroAgent(AgentRuntimeMixin):
    name = "financeiro_agent"

    def __init__(
        self,
        llm,
        telemetry=None,
        tool_router=None,
        rag_service=None,
        cache=None,
        settings=None,
        observer=None,
        memory=None,
        summary_memory=None,
    ):
        self.llm = llm
        self.telemetry = telemetry
        self.tool_router = tool_router
        self.rag_service = rag_service
        self.cache = cache
        self.settings = settings
        self.observer = observer
        self.memory = memory
        self.summary_memory = summary_memory

    async def run(self, state):
        await self._emit_ic("IC.FINANCEIRO_AGENT_STARTED", state, {})
        tool_context = await self._collect_mcp_context(state)
        rag_context, rag_metadata = await self._retrieve_rag_context(state)
        response = await self._invoke_llm_cached(
            state,
            "FinanceiroAgent",
            [
                {"role": "system", "content": "Você é um agente financeiro."},
                {"role": "user", "content": state.get("sanitized_input") or state.get("user_text", "")},
            ],
        )
        await self._emit_ic("IC.FINANCEIRO_AGENT_COMPLETED", state, {})
        return {
            "response_text": response,
            "mcp_results": tool_context,
            "rag_metadata": rag_metadata,
        }
```

### Ordem de Confiança dos Dados

1. `tool_arguments`
2. `business_context`
3. `context`
4. `session.metadata`
5. `state`
6. extração complementar do texto

### Prompt Policy

```yaml
prompt_policy:
  system_prompt_path: prompts/system.md
  response_style: concise
  require_evidence: true
  allow_tool_usage: true
```

### Guardrails por Agente

```yaml
input:
  - code: FIN_INPUT_POLICY
    enabled: true
    mode: observe

output:
  - code: FIN_OUTPUT_COMPLIANCE
    enabled: true
    mode: enforce
```

### Judges por Agente

```yaml
judges:
  - name: response_quality
    enabled: true
    threshold: 0.75
  - name: groundedness
    enabled: true
    threshold: 0.70
```

### Dataset de Eval

```yaml
dataset:
  name: financeiro_agent_regression
  version: 1.0.0
  items:
    - id: fin-001
      input: "Quero consultar minha fatura"
      business_context:
        customer_key: "11999999999"
        contract_key: "3000131180"
      expected:
        route: financeiro_agent
        tools:
          - consultar_fatura
        min_scores:
          quality: 0.75
          groundedness: 0.70
```


### Contrato obrigatório para agentes transacionais

Ao criar um agente que usa tools transacionais do framework, o desenvolvedor não deve criar um motor paralelo de coleta/confirmação. Deve reutilizar `AgentRuntime` e garantir que o `AgentState` do host mantenha o latch durável:

```python
active_transaction: dict[str, Any]
last_transaction: dict[str, Any]
```

Durante uma transação ativa, parâmetros já coletados são preservados e novos valores são mesclados incrementalmente. Em `COLLECTING_PARAMETERS`, uma resposta que satisfaz um parâmetro pendente tem precedência sobre keywords genéricas. Mudanças de intenção explícitas e inequívocas continuam permitidas.

Antes de publicar um novo template/host, execute os cenários multi-turno descritos no [`Transaction State Developer Guide`](../docs/TRANSACTION_STATE_DEVELOPER_GUIDE.md).


### Testes

| Teste | Escopo |
|---|---|
| Unitário | Classe do agente. |
| Routing | Intent e rota. |
| MCP Mapping | BusinessContext para argumentos. |
| Guardrails | Entrada e saída. |
| Judges | Scores mínimos. |
| Runtime | Execução completa. |
| Memory | Continuidade de conversa. |
| Checkpoint | Resume/replay. |
| Observability | Trace e eventos. |
| Certification | Evidências finais. |

### Definition of Done

- agente registrado;
- rota configurada;
- tools declaradas;
- mapping definido;
- prompts versionados;
- guardrails configurados;
- judges configurados;
- dataset criado;
- testes executados;
- traces gerados;
- certification suite aprovada;
- documentação do agente atualizada.

### Anti-patterns

- agente criando sessão;
- agente abrindo SSE;
- agente compilando LangGraph;
- agente chamando sistema externo diretamente;
- prompt hardcoded sem política;
- lógica genérica duplicada no agente;
- payload bruto de canal dentro do agente;
- ausência de dataset de eval.


### Requisitos Não Funcionais

| Categoria | Requisito |
|---|---|
| Disponibilidade | Componentes deployáveis expõem `/health` e `/ready`. |
| Escalabilidade | Apps stateless escalam horizontalmente. Estado conversacional fica em repositórios externos. |
| Segurança | Segredos são fornecidos por secret store ou Kubernetes Secrets. |
| Observabilidade | Logs, métricas e traces usam correlação por request_id, trace_id, session_id, tenant_id e agent_id. |
| Auditabilidade | Decisões de rota, guardrail, judge, MCP e LLM são rastreáveis. |
| Portabilidade | Execução suportada em local, Docker Compose e Kubernetes/OKE. |
| Configuração | Comportamento variável é controlado por `.env` e YAML versionado. |


### Critérios de Aceite

- [ ] Novo agente é criado sem alterar core do framework.
- [ ] Se houver transações multi-turno, `AgentState` declara `active_transaction` e `last_transaction`.
- [ ] Configuração ocorre por YAML e `.env`.
- [ ] Agente usa BusinessContext.
- [ ] Agente acessa MCP por router/gateway.
- [ ] Agente não conhece payload bruto de canal.
- [ ] Guardrails e judges são configurados.
- [ ] Dataset de eval existe.
- [ ] Testes mínimos executam.
- [ ] Trace completo é gerado.
- [ ] Definition of Done é atendida.


### Glossário

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
