# Correção TIM Observer Payload / NOC OTel

Esta versão corrige dois gaps da migração do `agent_framework_oci`:

1. **Pub/Sub flat**: eventos IC/GRL/analytics passam a ser publicados no contrato flat combinado com Data/TIM, sem envelope `{type, payload}` e sem `payload.payload`.
2. **NOC em OpenTelemetry Logs**: eventos NOC passam a ter caminho dedicado para OTel Logs, separado de traces/spans.
3. **Sequence automático**: eventos Pub/Sub flat passam a receber `sequence` incremental por `agentId/sessionId`, preservando valor explícito quando já vier no evento.

## Arquivos alterados/adicionados

- `src/agent_framework/analytics/tim_payload_mapper.py`
  - Novo mapper canônico para converter o envelope interno do framework para o payload TIM flat.
  - Mantém campos canônicos na raiz.
  - Mantém apenas `agentSpecificData` como objeto aninhado.

- `src/agent_framework/analytics/providers/pubsub.py`
  - Publica flat por padrão.
  - Mantém modo legado por configuração.
  - Exclui `NOC.*` do Pub/Sub por padrão, seguindo a lib antiga.
  - Injeta `sequence` automaticamente no payload flat antes do publish.

- `src/agent_framework/analytics/tim_sequence.py`
  - Novo gerador de sequence por `agentId/sessionId`.
  - Suporta Redis `INCR` como contador atômico cross-worker/cross-pod.
  - Suporta MongoDB com `find_one_and_update` + `$inc`, mantendo paridade com a lib antiga.
  - Usa fallback em memória quando o backend compartilhado não estiver disponível, sem quebrar o fluxo de observabilidade.
  - Preserva `sequence` explícito quando o chamador já informou o campo.

- `src/agent_framework/observability/noc_otel.py`
  - Novo exportador dedicado de NOC para OpenTelemetry Logs.
  - Usa `OTLPLogExporter` e `LoggingHandler`.
  - Aplica DE/PARA flat com `keep_none=True`.
  - Achata dict/list para string JSON antes de enviar ao OTel.

- `src/agent_framework/observability/observer.py`
  - `emit_noc()` agora dispara o canal dedicado de OTel Logs antes da publicação analytics.

- `src/agent_framework/config/settings.py`
  - Novas variáveis de configuração.

## Novas variáveis

```env
# Pub/Sub: padrão corrigido para TIM/Data
PUBSUB_PAYLOAD_MODE=flat
PUBSUB_EXCLUDE_NOC=true

# Sequence automático por sessão no payload Pub/Sub flat
PUBSUB_SEQUENCE_ENABLED=true

# auto = Redis se configurado; senão MongoDB se configurado; senão fallback em memória.
# Para o BO sem OCI Cache, usar mongodb para manter paridade com a lib antiga.
PUBSUB_SEQUENCE_PROVIDER=mongodb

# Opção Redis, quando existir cache disponível
# PUBSUB_SEQUENCE_REDIS_URL=redis://localhost:6379/0

# Opção MongoDB, equivalente ao comportamento antigo via find_one_and_update + $inc
PUBSUB_SEQUENCE_MONGODB_URI=mongodb://localhost:27017
PUBSUB_SEQUENCE_MONGODB_DATABASE=agent_platform
PUBSUB_SEQUENCE_MONGODB_COLLECTION=${AGENT_NAME}_event_counters

PUBSUB_SEQUENCE_TTL_SECONDS=86400
PUBSUB_SEQUENCE_MEMORY_FALLBACK=true
PUBSUB_SEQUENCE_KEY_PREFIX=observer:sequence

# Para voltar temporariamente ao formato antigo envelopado
# PUBSUB_PAYLOAD_MODE=legacy

# NOC via OpenTelemetry Logs
ENABLE_NOC_OTEL_LOGS=true
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://10.153.35.23/v1/logs
OTEL_EXPORTER_OTLP_HOST_HEADER=tim-ai-atend-agnt-opentelemetry
OTEL_SERVICE_NAME=ai-agent-template
```

## Exemplo de Pub/Sub corrigido

```json
{
  "eventType": "IC.FATURA_CONSULTADA",
  "version": "1.0",
  "eventDate": "2026-06-19T12:00:00+00:00",
  "sessionId": "sess-789",
  "channelId": "whatsapp",
  "agentId": "billing-agent",
  "tag": "IC.FATURA_CONSULTADA",
  "sequence": 12,
  "agentSpecificData": {
    "invoiceId": "INV-001"
  }
}
```

## Observação

O envelope interno retornado pelo `observer.emit(...)` foi mantido para não quebrar EventBus, Langfuse ou consumidores internos. A correção ocorre no provider Pub/Sub e no novo canal NOC OTel.


## Sequence automático

No modo flat, o provider Pub/Sub chama `ensure_sequence(message)` antes de publicar.

Com `sessionId` presente e sem `sequence` explícito, o framework gera:

```text
observer:sequence:<agentId>:<sessionId> -> INCR
```

Exemplo:

```json
{ "eventType": "IC.001", "sessionId": "sess-1", "agentId": "billing", "sequence": 1 }
{ "eventType": "IC.002", "sessionId": "sess-1", "agentId": "billing", "sequence": 2 }
{ "eventType": "IC.003", "sessionId": "sess-1", "agentId": "billing", "sequence": 3 }
```

Regras:

- Se `sequence` já vier no metadata/payload, ele é preservado.
- Se `sessionId` não existir, o campo não é gerado.
- MongoDB é suportado para cenários sem OCI Cache/Redis e usa operação atômica `find_one_and_update` com `$inc`, como na lib antiga.
- Redis continua suportado quando houver cache disponível, pois `INCR` é atômico entre workers/pods.
- O fallback em memória é apenas best-effort local para ambientes de desenvolvimento ou contingência.


### Sequence com MongoDB

Para ambientes do BO onde não existe OCI Cache/Redis dimensionado, configure:

```env
PUBSUB_SEQUENCE_ENABLED=true
PUBSUB_SEQUENCE_PROVIDER=mongodb
PUBSUB_SEQUENCE_MONGODB_URI=mongodb://<host>:27017
PUBSUB_SEQUENCE_MONGODB_DATABASE=agent_platform
PUBSUB_SEQUENCE_MONGODB_COLLECTION=${AGENT_NAME}_event_counters
PUBSUB_SEQUENCE_TTL_SECONDS=86400
PUBSUB_SEQUENCE_MEMORY_FALLBACK=true
```

O documento no Mongo usa `_id` igual à chave lógica:

```text
observer:sequence:<agentId>:<sessionId>
```

A atualização é atômica:

```python
find_one_and_update(
    {"_id": key},
    {"$inc": {"sequence": 1}},
    upsert=True,
    return_document=AFTER,
)
```

Também é criado, em best-effort, um índice TTL sobre `expiresAt`. Se o usuário Mongo não tiver permissão para criar índice, a geração de sequence continua funcionando; apenas a limpeza automática pode depender de rotina externa.

### Collection Mongo compatível com legado

Quando `PUBSUB_SEQUENCE_PROVIDER=mongodb`, a collection dos contadores pode ser informada explicitamente:

```env
PUBSUB_SEQUENCE_MONGODB_COLLECTION=telecom_contas_event_counters
```

Se essa variável não for definida, o framework usa o padrão legado:

```text
{AGENT_NAME}_event_counters
```

Também são aceitos, por compatibilidade operacional:

```env
MONGODB_EVENT_COUNTERS_COLLECTION=telecom_contas_event_counters
EVENT_COUNTERS_COLLECTION=telecom_contas_event_counters
```
