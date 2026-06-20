# AI Agent Platform — Enterprise Routing Edition

Esta versão inclui o projeto completo com:

- `agent_framework`: framework reutilizável.
- `agent_template_backend`: backend FastAPI com LangGraph, OCI Generative AI, Langfuse, guardrails, judges, supervisor e roteamento enterprise.
- `agent_frontend`: frontend web independente.
- `templates/template_telecom_billing_product`: template de exemplo para telecom com agentes de Fatura e Produto.
- `templates/template_retail_orders_support`: template de exemplo para e-commerce com agentes de Pedido e Suporte.

## Roteamento enterprise

O roteamento fica em:

```text
agent_framework/src/agent_framework/routing/
```

Componentes principais:

- `models.py`: modelos `IntentDefinition`, `RouterStatePolicy`, `RouteDecision`.
- `config_loader.py`: carrega o YAML de intents e políticas.
- `enterprise_router.py`: decide o agente de destino por estado, keyword, LLM ou fallback.

O template usa:

```text
agent_template_backend/config/routing.yaml
```

## Ordem de decisão

1. Estado conversacional (`state_policies`).
2. Keywords/intents configuráveis.
3. LLM Router opcional (`ENABLE_LLM_ROUTER=true`).
4. Fallback (`router.fallback_agent`).

## Como testar roteamento sem chamar o agente final

```bash
curl -X POST http://localhost:8000/debug/route \
  -H 'Content-Type: application/json' \
  -d '{
    "channel": "web",
    "payload": {
      "text": "Minha fatura veio alta",
      "user_id": "u1",
      "channel_id": "browser-1",
      "context": {"msisdn": "5511999999999"}
    }
  }'
```

Resposta esperada:

```json
{
  "route": "billing_agent",
  "agent": "billing_agent",
  "intent": "billing_invoice_explanation",
  "method": "keyword"
}
```

## Como habilitar roteamento por LLM

No `.env` do backend:

```env
LLM_PROVIDER=oci_openai
OCI_GENAI_API_KEY=...
OCI_GENAI_BASE_URL=https://inference.generativeai.sa-saopaulo-1.oci.oraclecloud.com/openai/v1
OCI_GENAI_MODEL=openai.gpt-4.1
ENABLE_LLM_ROUTER=true
ROUTING_CONFIG_PATH=./config/routing.yaml
```

## Como adicionar novo agente

1. Criar classe do agente em `agent_template_backend/app/agents/`.
2. Instanciar o agente em `AgentWorkflow.__init__`.
3. Adicionar node no LangGraph.
4. Adicionar a rota no `add_conditional_edges`.
5. Criar intent no `config/routing.yaml` apontando `agent: nome_do_agente`.

## Templates incluídos

### Template 1 — Telecom

Diretório:

```text
templates/template_telecom_billing_product
```

Agentes:

- BillingAgent
- ProductAgent

### Template 2 — Retail/E-commerce

Diretório:

```text
templates/template_retail_orders_support
```

Agentes:

- OrdersAgent
- SupportAgent

Este segundo template mostra como reutilizar a mesma arquitetura para outro domínio de negócio.
