# Template Backend/Frontend alinhado ao BusinessContext v2

Este pacote atualiza o `agent_template_backend` e o `agent_frontend` para refletir o framework novo, onde as chaves vindas do canal/front-end são resolvidas uma vez como chaves canônicas e propagadas pelas camadas até o MCP Server.

## Fluxo implementado

1. O front-end envia `tenant_id`, `agent_id`, `session_id` e `business_context`.
2. O backend normaliza a mensagem via `ChannelGateway` preservando todo o payload no `context`.
3. O backend usa `IdentityResolver` com `config/identity.yaml` para gerar `BusinessContext`:
   - `customer_key`
   - `contract_key`
   - `interaction_key`
   - `account_key`
   - `resource_key`
   - `session_key`
4. O workflow recebe `context.business_context`.
5. Os agentes de exemplo não montam mais argumentos específicos como `msisdn`, `invoice_id` ou `order_id` diretamente.
6. O `MCPToolRouter` usa `config/mcp_parameter_mapping.yaml` para converter chaves canônicas em parâmetros reais de cada tool MCP.

## Arquivos principais ajustados

- `agent_template_backend/app/main.py`
  - carrega `IdentityResolver`;
  - resolve `BusinessContext` por mensagem;
  - persiste as chaves na sessão/memória/metadata/SSE;
  - adiciona `/debug/identity`.

- `agent_template_backend/app/agents/runtime.py`
  - adiciona `_collect_mcp_context()` centralizado;
  - repassa `business_context` e `original_context` para o MCP Router.

- `agent_template_backend/app/agents/*_agent.py`
  - agentes passam a usar `_collect_mcp_context()` em vez de montar argumentos específicos.

- `agent_template_backend/config/identity.yaml`
  - define como campos do canal/front-end alimentam as chaves canônicas.

- `agent_template_backend/config/mcp_parameter_mapping.yaml`
  - define como chaves canônicas viram parâmetros reais por tool MCP.

- `agent_frontend/index.html` e `agent_frontend/app.js`
  - adicionam campos de `tenant`, `agent` e chaves canônicas;
  - enviam `business_context` no payload;
  - mantêm aliases de domínio para compatibilidade (`msisdn`, `invoice_id`, `order_id`, etc.).

## Teste rápido

Suba backend, frontend e MCP servers. Depois teste:

```bash
curl -s http://localhost:8000/health | jq

curl -s -X POST http://localhost:8000/debug/identity \
  -H 'Content-Type: application/json' \
  -d '{
    "channel":"web",
    "tenant_id":"default",
    "agent_id":"telecom_contas",
    "payload":{
      "message":"Minha fatura veio alta",
      "session_id":"teste-001",
      "msisdn":"11999999999",
      "invoice_id":"3000131180",
      "ura_call_id":"URA-123",
      "business_context":{
        "customer_key":"11999999999",
        "contract_key":"3000131180",
        "interaction_key":"URA-123",
        "session_key":"teste-001"
      }
    }
  }' | jq

curl -s -X POST http://localhost:8000/debug/mcp/call/consultar_fatura \
  -H 'Content-Type: application/json' \
  -d '{
    "business_context": {
      "customer_key":"11999999999",
      "contract_key":"3000131180",
      "interaction_key":"URA-123",
      "session_key":"teste-001"
    }
  }' | jq
```

No log do backend, procure por `mcp.tool.mapped`. Ele deve indicar as chaves mapeadas e `has_msisdn=true`, `has_invoice_id=true` para o domínio telecom.
