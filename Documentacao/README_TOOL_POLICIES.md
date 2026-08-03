# Políticas mínimas para tools MCP read-only e transacionais

## Objetivo

O framework diferencia operações de consulta (`read_only`) e operações que alteram estado (`transactional`) imediatamente antes da chamada MCP. Essa classificação não substitui autorização, idempotência ou regras de negócio do servidor MCP; ela acrescenta somente a proteção conversacional mínima, especialmente confirmação explícita.

## Onde configurar

A parametrização pertence ao backend da aplicação:

```text
templates/agent_template_backend/config/tool_policies.yaml
```

A biblioteca compartilhada contém apenas o loader e a validação. O caminho é opcional:

```dotenv
TOOL_POLICIES_PATH=./config/tool_policies.yaml
```

## Exemplo

```yaml
version: 1

defaults:
  operation_type: read_only
  require_confirmation: false

tool_policies:
  consultar_plano:
    operation_type: read_only

  alterar_plano:
    operation_type: transactional
    require_confirmation: true
    requires: [new_plan_id]
```

Para executar `alterar_plano`, os argumentos precisam conter `new_plan_id` e um booleano literal de confirmação:

```json
{"new_plan_id": "CONTROLE_100", "confirmed": true}
```

Também é aceito `"confirmation": true`. Strings como `"true"` não são aceitas como confirmação.

## Compatibilidade

- Se `tool_policies.yaml` não existir, o framework continua usando `tool_type`, `requires`, `confirmation_required` e `execution_policy` de `tools.yaml`.
- Tools antigas sem política continuam executando como antes.
- Uma política explícita no arquivo novo prevalece para `operation_type` e confirmação daquela tool.
- O catálogo `tools.yaml` continua sendo a fonte de endpoint, schema, habilitação e cache.
- O novo arquivo não deve ser colocado em `libs/agent_framework`, pois as decisões variam por aplicação e domínio.

## Fluxo de execução

```text
agente -> MCPToolRouter -> validação da política -> mapeamento de parâmetros -> MCP Gateway/Server
```

Uma chamada bloqueada retorna `ok=false`, `metadata.blocked_by_policy=true`, o tipo da operação e a origem da política. O servidor MCP permanece a autoridade final para autenticação, autorização, validação, idempotência e transação de negócio.

## Migração recomendada

1. Atualize a biblioteca sem criar o arquivo: o comportamento permanece legado.
2. Crie `config/tool_policies.yaml` no backend.
3. Cadastre primeiro apenas operações transacionais que exigem confirmação.
4. Teste chamadas sem confirmação, com confirmação booleana e com campos obrigatórios ausentes.
5. Remova gradualmente duplicações de confirmação de `tools.yaml` quando todos os templates consumidores já usarem a nova configuração.


## Runtime transacional mínimo (correção de amarração)

A lista `mcp_tools` do roteamento é uma **allowlist**, não uma ordem para executar todas as ferramentas. O runtime agora:

1. executa automaticamente somente ferramentas `read_only`;
2. seleciona no máximo uma ação transacional compatível com o pedido do usuário;
3. quando `require_confirmation: true`, persiste `pending_tool_call` e `transaction_status: AWAITING_CONFIRMATION`;
4. no turno de confirmação, reutiliza a mesma chamada e executa com `confirmed: true`;
5. publica no estado `available_mcp_tools`, `selected_tool_call`, `tool_policy_result`, `confirmation_required` e `confirmation_received`.

Para o cenário de exemplo, o pedido `123` (ou `PED-ENTREGUE`) retorna `ENTREGUE` no MCP Retail. Use:

```text
Quero devolver o pedido 123 porque me arrependi da compra.
Sim, confirmo a devolução.
```

O contrato MCP foi padronizado para usar `reason` tanto no catálogo quanto no servidor FastMCP. `tool_policies.yaml` prevalece sobre os campos legados de `tools.yaml`; estes permanecem alinhados nos templates para compatibilidade.
