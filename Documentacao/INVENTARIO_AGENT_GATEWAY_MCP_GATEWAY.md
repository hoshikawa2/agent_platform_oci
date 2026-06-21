# Inventário — Agent Gateway + MCP Gateway Overlay

Este inventário lista os arquivos incluídos no overlay `agent_platform_agent_gateway_mcp_gateway_overlay.zip`, indicando a área, o tipo de alteração e a finalidade de cada arquivo.

## Resumo

| Área | Quantidade |
|---|---:|
| Documentação | 1 |
| Agent Gateway | 10 |
| MCP Gateway | 5 |
| Agent Framework | 4 |
| Template Backend | 2 |
| MCP Server Mock | 2 |
| Deploy | 2 |

## Arquivos por área

### Documentação

| Arquivo | Tipo | Finalidade |
|---|---|---|
| `README_AGENT_GATEWAY_AND_MCP_GATEWAY_EVOLUTION.md` | Novo / overlay | Documento principal do overlay. Explica a nova arquitetura sem AI Gateway separado, com Agent Gateway governando políticas/modelos e MCP Gateway separado para tools. |

### Agent Gateway

| Arquivo | Tipo | Finalidade |
|---|---|---|
| `apps/agent_gateway/app/config/governance_loader.py` | Novo / overlay | Carrega o arquivo YAML de governança do Agent Gateway a partir de AGENT_GATEWAY_GOVERNANCE_CONFIG. |
| `apps/agent_gateway/app/governance/__init__.py` | Novo / overlay | Inicializa o pacote Python de governança do Agent Gateway. |
| `apps/agent_gateway/app/governance/audit.py` | Novo / overlay | Centraliza logging/auditoria das decisões de governança do Agent Gateway, com proteção simples para não logar mensagem completa. |
| `apps/agent_gateway/app/governance/evaluation_hooks.py` | Novo / overlay | Hooks antes e depois da chamada ao backend/runtime. Serve para amostragem, evaluator, scoring ou integração futura com Langfuse. |
| `apps/agent_gateway/app/governance/model_policies.py` | Novo / overlay | Resolve políticas de modelo/profile no Agent Gateway. Define qual provider/model/profile deve ser usado por operação, tenant e agente. |
| `apps/agent_gateway/app/governance/rate_limit.py` | Novo / overlay | Implementa rate limit em memória por tenant, agente e canal antes de encaminhar a requisição ao backend/runtime. |
| `apps/agent_gateway/app/governance/usage.py` | Novo / overlay | Hook para registrar uso de gateway, políticas aplicadas e respostas do backend. Pronto para plugar métricas, banco, Langfuse ou OTEL. |
| `apps/agent_gateway/app/governance_middleware.py` | Novo / overlay | Componente principal de governança do Agent Gateway. Aplica rate limit, resolve model_policy, gera headers/metadados e executa hooks antes/depois do backend. |
| `apps/agent_gateway/app/routes/governed_proxy_example.py` | Novo / overlay | Exemplo de rota governada para demonstrar como aplicar governança antes de encaminhar para o Agent Backend/Runtime. |
| `apps/agent_gateway/config/gateway_governance.yaml` | Novo / overlay | Configuração de governança do Agent Gateway: profiles, operation_profiles, providers permitidos, rate limits, headers propagados e evaluation hooks. |

### MCP Gateway

| Arquivo | Tipo | Finalidade |
|---|---|---|
| `apps/mcp_gateway/Dockerfile` | Novo / overlay | Imagem Docker do MCP Gateway. |
| `apps/mcp_gateway/app/__init__.py` | Novo / overlay | Inicializa o pacote Python da aplicação MCP Gateway. |
| `apps/mcp_gateway/app/main.py` | Novo / overlay | Aplicação FastAPI do MCP Gateway. Expõe health, ready, catálogo de tools e endpoint de invoke com auth, autorização, mapping, cache, timeout e retry. |
| `apps/mcp_gateway/config/mcp_gateway.yaml` | Novo / overlay | Configuração central do MCP Gateway: MCP servers, tools, versões, cache, timeout, retry, autorização por agente/canal e mapping BusinessContext → parâmetros. |
| `apps/mcp_gateway/requirements.txt` | Novo / overlay | Dependências Python do MCP Gateway. |

### Agent Framework

| Arquivo | Tipo | Finalidade |
|---|---|---|
| `libs/agent_framework/src/agent_framework/gateway_policy_context.py` | Novo / overlay | Helper no framework para o Runtime ler a política de modelo enviada pelo Agent Gateway em state['metadata']['model_policy']. |
| `libs/agent_framework/src/agent_framework/gateways/__init__.py` | Novo / overlay | Inicializa o pacote de clients de gateways no framework, exportando MCPGatewayClient. |
| `libs/agent_framework/src/agent_framework/gateways/mcp_gateway_client.py` | Novo / overlay | Client assíncrono do framework para chamar o MCP Gateway: listar tools e executar tools. |
| `libs/agent_framework/src/agent_framework/runtime_mcp_gateway_adapter.py` | Novo / overlay | Mixin opcional para agentes/runtime chamarem tools via MCP Gateway e anexarem resultados em state['mcp_results']. |

### Template Backend

| Arquivo | Tipo | Finalidade |
|---|---|---|
| `templates/agent_template_backend/app/mcp_gateway_client_factory.py` | Novo / overlay | Factory no template backend para construir MCPGatewayClient a partir de variáveis de ambiente. |

### MCP Server Mock

| Arquivo | Tipo | Finalidade |
|---|---|---|
| `mcp/servers/mock_telecom_mcp/app.py` | Novo / overlay | Mock MCP Server com tools consultar_fatura e consultar_pagamentos para validar o MCP Gateway localmente. |
| `mcp/servers/mock_telecom_mcp/requirements.txt` | Novo / overlay | Dependências do mock MCP Server de telecom usado para testes locais. |

### Deploy

| Arquivo | Tipo | Finalidade |
|---|---|---|
| `deploy/docker/docker-compose.mcp-gateway.yml` | Novo / overlay | Docker Compose para subir MCP Gateway e mock_telecom_mcp localmente. |
| `deploy/k8s/mcp-gateway.yaml` | Novo / overlay | Manifest Kubernetes de Deployment e Service do MCP Gateway. |

## Observações de integração

### Agent Gateway

Os arquivos em `apps/agent_gateway` não criam um novo serviço. Eles evoluem o Agent Gateway existente para atuar como gateway dedicado da plataforma, centralizando:

- políticas de modelo/profile;
- rate limit;
- auditoria;
- hooks de avaliação;
- propagação de metadados de governança para o Runtime.

A rota `governed_proxy_example.py` é um exemplo de integração. O handler real do `POST /gateway/message` deve aplicar:

```python
governed_body, headers = governance.prepare_backend_request(body)
```

antes de chamar o backend/runtime, e:

```python
return governance.process_backend_response(data)
```

após receber a resposta.

### MCP Gateway

O MCP Gateway é um serviço separado. Ele centraliza:

- catálogo de tools;
- autorização por agente/canal;
- versionamento de tools;
- mapping de BusinessContext para parâmetros;
- cache;
- timeout;
- retry;
- auditoria simples.

### Runtime / Backend

O Runtime continua responsável por:

- LangGraph;
- estado;
- memória;
- checkpoints;
- fluxo;
- providers LLM existentes.

O Runtime passa a chamar tools via MCP Gateway usando `MCPGatewayClient` e/ou `MCPGatewayRuntimeMixin`.

### AI Gateway

Este overlay não cria `apps/ai_gateway`. A governança de modelo fica no Agent Gateway, e a execução LLM continua no Runtime/backend usando os providers já existentes.
