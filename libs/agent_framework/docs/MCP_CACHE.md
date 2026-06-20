# MCP Cache

O cache MCP é configurado diretamente no `config/tools.yaml`, dentro da própria tool.

Não existe regra chumbada por nome, idioma ou prefixo. Uma tool só usa cache quando declarar explicitamente:

```yaml
tools:
  consultar_fatura:
    description: Consulta dados resumidos de fatura por msisdn/invoice_id.
    mcp_server: telecom
    enabled: true
    cache:
      enabled: true
      ttl_seconds: 600
    args_schema:
      msisdn: string
      invoice_id: string
```

Tools sem bloco `cache` não usam cache por padrão:

```yaml
tools:
  consultar_titulo_financeiro:
    description: Consulta um título financeiro por cliente e contrato.
    mcp_server: telecom
    enabled: true
    args_schema:
      customer_id: string
      contract_id: string
```

Tools de ação devem ficar sem cache ou com cache explicitamente desabilitado:

```yaml
tools:
  solicitar_troca:
    description: Simula abertura de solicitação de troca.
    mcp_server: retail
    enabled: true
    tool_type: action
    requires: [order_id, reason]
    confirmation_required: false
    cache:
      enabled: false
    args_schema:
      order_id: string
      reason: string
```


## Como a `cache_key` é montada

A chave de cache MCP precisa ser determinística. Ela não pode depender de valores que mudam a cada turno, como `session_id`, `request_id`, `trace_id`, `timestamp`, `intent`, `agent_id` ou `business_context` completo.

A regra implementada é:

```text
mesma tool + mesmos campos declarados no args_schema + mesmos valores = mesma cache_key
```

Exemplo:

```yaml
tools:
  consultar_fatura:
    cache:
      enabled: true
      ttl_seconds: 600
```

Com isso, estas duas chamadas geram a mesma chave:

```json
{
  "msisdn": "11999999999",
  "invoice_id": "12345"
}
```

```json
{
  "invoice_id": "12345",
  "msisdn": "11999999999",
  "session_id": "valor-que-muda",
  "trace_id": "valor-que-muda"
}
```

A chave considera automaticamente apenas `msisdn` e `invoice_id` porque eles estão declarados em `args_schema`. Atributos auxiliares fora do contrato da tool são ignorados.

Não é necessário declarar `key_fields` no YAML. A fonte da verdade para a chave é o próprio `args_schema` da tool.

## Configurações globais

```env
ENABLE_MCP_CACHE=true
MCP_CACHE_TTL_SECONDS=300
TOOLS_CONFIG_PATH=./config/tools.yaml
```

`MCP_CACHE_TTL_SECONDS` é apenas fallback. O TTL preferencial vem de cada tool.

## Fluxo

```text
AgentRuntimeMixin._call_mcp_tool()
  ↓
Lê política cache da tool em tools.yaml
  ↓
Monta cache_key por tool_name + campos declarados no args_schema
  ↓
cache ausente/false → IC.MCP_CACHE_BYPASS → chama MCP normalmente
cache.enabled=true  → tenta cache
  ↓
cache hit  → IC.MCP_CACHE_HIT → retorna resultado salvo
cache miss → IC.MCP_CACHE_MISS → chama MCP Router
  ↓
ok=true  → IC.MCP_CACHE_SET → salva no cache com TTL da tool
ok=false → IC.MCP_CACHE_NOT_STORED → não salva
```

## Evidências operacionais

O runtime grava logs:

```text
MCP cache bypass
MCP cache hit
MCP cache miss
MCP cache set
MCP cache not stored
```

O runtime também emite eventos IC. Nos eventos `HIT`, `MISS`, `SET` e `NOT_STORED`, o payload inclui `cache_key` e `cache_key_payload` para auditoria:

```text
IC.MCP_CACHE_BYPASS
IC.MCP_CACHE_HIT
IC.MCP_CACHE_MISS
IC.MCP_CACHE_SET
IC.MCP_CACHE_NOT_STORED
```

E eventos de telemetria:

```text
cache.mcp.hit
cache.mcp.miss
cache.mcp.set
```

## Onde está implementado

- `src/agent_framework/runtime/agent_runtime.py`
- `src/agent_framework/mcp/models.py`
- `src/agent_framework/mcp/registry.py`
- `config/tools.yaml`

## Regra de segurança

O default é `cache.enabled=false`. Isso evita cache acidental em tools mutáveis, como abertura de chamado, troca, devolução, cancelamento ou alteração cadastral.

## Exemplo de evidência esperada

Primeira chamada:

```text
IC.MCP_CACHE_MISS  tool=consultar_fatura
IC.MCP_CACHE_SET   tool=consultar_fatura ttl_seconds=600
```

Segunda chamada com os mesmos `msisdn` e `invoice_id`:

```text
IC.MCP_CACHE_HIT   tool=consultar_fatura
```

Se a segunda chamada gerar `MISS`, confira o `cache_key_payload`. Ele deve conter os mesmos argumentos efetivos enviados ao MCP.


## Ordem correta dos eventos

Na primeira chamada cacheável:

```text
IC.MCP_TOOL_REQUESTED
IC.MCP_CACHE_MISS
IC.MCP_TOOL_EXECUTING
IC.MCP_TOOL_EXECUTED
IC.MCP_CACHE_SET
IC.TOOL_CALLED cached=false
```

Na segunda chamada com os mesmos campos de `args_schema`:

```text
IC.MCP_TOOL_REQUESTED
IC.MCP_CACHE_HIT
IC.TOOL_CALLED cached=true
```

Quando houver `IC.MCP_CACHE_HIT`, não deve aparecer `IC.MCP_TOOL_EXECUTING` nem `IC.MCP_TOOL_EXECUTED`, porque o MCP Server não foi chamado.
