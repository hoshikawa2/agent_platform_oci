# Atualização do Template Backend — Analytics, Observer, NOC/GRL e OutputSupervisor

Esta versão do `agent_template_backend` foi atualizada para consumir as novidades transportadas para o `agent_framework`.

## 1. Analytics e Pub/Sub

O backend não chama mais diretamente apenas o publisher antigo de eventos. Agora ele cria um `AnalyticsPublisher`:

```python
from agent_framework.analytics.factory import create_analytics_publisher
from agent_framework.observability.observer import AgentObserver

analytics = create_analytics_publisher(settings)
observer = AgentObserver(analytics=analytics)
```

Com isso, o mesmo backend pode publicar em:

- OCI Streaming
- GCP Pub/Sub
- CompositePublisher, quando `ANALYTICS_PROVIDERS=oci_streaming,pubsub`
- Noop, quando analytics estiver desligado

## 2. Configuração mínima

```env
ENABLE_ANALYTICS=true
ANALYTICS_PROVIDERS=pubsub
GCP_PUBSUB_TOPIC_PATH=projects/<project-id>/topics/<topic-name>
GOOGLE_APPLICATION_CREDENTIALS=/secrets/gcp-service-account.json
```

Para publicar simultaneamente em OCI Streaming e GCP Pub/Sub:

```env
ENABLE_ANALYTICS=true
ANALYTICS_PROVIDERS=oci_streaming,pubsub
ENABLE_OCI_STREAMING=true
OCI_STREAM_ENDPOINT=<endpoint>
OCI_STREAM_OCID=<stream-ocid>
GCP_PUBSUB_TOPIC_PATH=projects/<project-id>/topics/<topic-name>
```

## 3. Observer corporativo

O workflow recebeu emissão automática dos principais eventos corporativos:

- `NOC.001`: início do workflow
- `NOC.005`: exceção fatal no workflow
- `NOC.006`: fim do workflow antes da resposta final
- `IC.AGENT_COMPLETED`: evento informacional de conclusão
- `GRL.001` a `GRL.009`: emitidos pelo `OutputSupervisor`

## 4. OutputSupervisor

Foi inserido um novo nó LangGraph:

```text
agent -> output_supervisor -> output_guardrails -> judge -> supervisor_review -> persist
```

O `OutputSupervisor` não substitui o supervisor de roteamento. Ele valida a saída candidata do agente usando o contrato corporativo:

- `allow`
- `sanitize`
- `retry`
- `block`
- `handover`
- `observe`

Para compatibilidade com os guardrails já existentes, o template inclui o adapter `LegacyOutputGuardrailRail`, que converte decisões antigas `allowed=True/False` para `RailAction`.

## 5. Campos adicionados ao AgentState

```python
supervisor_action: str
supervisor_guidance: str
supervisor_attempt: int
supervisor_handover_reason: str
output_supervisor_results: list[dict]
output_guardrails_already_applied: bool
```

## 6. Arquivos alterados

- `agent_template_backend/app/main.py`
- `agent_template_backend/app/workflows/agent_graph.py`
- `agent_template_backend/app/state.py`
- `agent_template_backend/.env`
- `agent_template_backend/requirements.txt`
- `agent_framework/src/agent_framework/config/settings.py`

## 7. Observação importante

O `OutputSupervisor` roda os guardrails de saída por meio do adapter legado e marca `output_guardrails_already_applied=True`. Assim o nó `output_guardrails` permanece no grafo para compatibilidade, mas evita reexecutar a mesma validação quando o supervisor já aplicou os rails.
