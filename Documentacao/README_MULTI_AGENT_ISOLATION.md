# Multi-agent isolation

Esta versão permite subir mais de um `agent_template` no mesmo backend e chavear por `agent_id` sem misturar estado.

## O que ficou isolado

A chave lógica usada pelo backend é:

```text
tenant_id:agent_id:session_id
```

Com isso ficam isolados:

- memória conversacional;
- checkpoints do LangGraph (`thread_id`);
- telemetria/tags;
- prompts por perfil de agente;
- configuração de guardrails por agente;
- configuração de judges por agente;
- metadados de sessão.

## Arquivo principal

```text
agent_template_backend/config/agents.yaml
```

Exemplo:

```yaml
default_agent_id: telecom_contas
agents:
  - agent_id: telecom_contas
    prompt_policy_path: ./config/agents/telecom_contas/prompt_policy.yaml
    guardrails_config_path: ./config/agents/telecom_contas/guardrails.yaml
    judges_config_path: ./config/agents/telecom_contas/judges.yaml

  - agent_id: retail_orders
    prompt_policy_path: ./config/agents/retail_orders/prompt_policy.yaml
    guardrails_config_path: ./config/agents/retail_orders/guardrails.yaml
    judges_config_path: ./config/agents/retail_orders/judges.yaml
```

## Como escolher o agente na chamada

### Telecom

```bash
curl -X POST http://localhost:8000/gateway/message \
  -H 'Content-Type: application/json' \
  -d '{
    "channel": "web",
    "agent_id": "telecom_contas",
    "tenant_id": "tim",
    "payload": {
      "session_id": "sessao-123",
      "user_id": "cliente-1",
      "message": "Quero entender minha fatura",
      "context": {"invoice_id": "FAT-001"}
    }
  }'
```

### Retail

```bash
curl -X POST http://localhost:8000/gateway/message \
  -H 'Content-Type: application/json' \
  -d '{
    "channel": "web",
    "agent_id": "retail_orders",
    "tenant_id": "loja",
    "payload": {
      "session_id": "sessao-123",
      "user_id": "cliente-1",
      "message": "Onde está meu pedido?",
      "context": {"order_id": "PED-001"}
    }
  }'
```

Mesmo usando o mesmo `session_id`, as conversas ficam separadas porque as chaves finais serão:

```text
tim:telecom_contas:sessao-123
loja:retail_orders:sessao-123
```

## Endpoints úteis

```text
GET /agents
GET /health
POST /debug/route
POST /gateway/message
```

## Como adicionar um novo agent_template

1. Crie uma pasta em `agent_template_backend/config/agents/<novo_agent_id>/`.
2. Adicione `prompt_policy.yaml`, `guardrails.yaml` e `judges.yaml`.
3. Registre o agente em `config/agents.yaml`.
4. Chame `/gateway/message` usando `agent_id=<novo_agent_id>`.

## Observação arquitetural

O backend continua usando um único processo FastAPI e um único framework instalado, mas o estado persistido não usa mais `session_id` sozinho. Isso evita que dois agentes compartilhem memória, checkpoints ou decisões de governança acidentalmente.
