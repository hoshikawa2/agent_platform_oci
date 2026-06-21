# Modular Remap - Agent Framework OCI

Esta entrega reorganiza o projeto para uma arquitetura corporativa modular, preservando o core existente e separando responsabilidades deployáveis.

## Mapa de remanejamento

| Origem | Destino |
|---|---|
| `agent_framework/` | `libs/agent_framework/` |
| `agent_gateway/` | `apps/agent_gateway/` |
| `channel_gateway/` | `apps/channel_gateway/` |
| `agent_frontend/` | `apps/agent_frontend/` |
| `agent_template_backend/` | `templates/agent_template_backend/` |
| `agent_template_backend_day_zero/` | `templates/agent_template_backend_day_zero/` |
| `mcp_servers/` | `mcp/servers/` |
| `agent_certification_tests/` | `evals/certification/` |
| `agent_framework_oci_evaluator/evaluator/` | `evals/offline/evaluator/` |

## Novos componentes

- `apps/ai_gateway`: camada de abstração e governança de modelos.
- `apps/mcp_gateway`: camada de roteamento e governança de MCP servers.
- `specs/`: documentação objetiva no formato Spec-Driven Development.
- `deploy/k8s/`: manifests iniciais para componentes deployáveis.

## Intenção arquitetural

O framework permanece como núcleo reutilizável. A reorganização explicita fronteiras de responsabilidade e prepara a solução para governança, escala e operação corporativa.
