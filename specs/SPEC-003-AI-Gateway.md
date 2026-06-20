# SPEC-003 — AI Gateway

## Escopo

O AI Gateway executa chamadas de inferência e embedding por contrato padronizado. Ele centraliza provider, modelo, profile, política, fallback, uso, custo, latência e telemetria.

## Endpoints

| Método | Endpoint | Descrição |
|---|---|---|
| `POST` | `/v1/chat/completions` | Geração de texto/chat. |
| `POST` | `/v1/embeddings` | Geração de embeddings. |
| `GET` | `/v1/models` | Lista modelos disponíveis. |
| `GET` | `/v1/profiles` | Lista profiles configurados. |
| `GET` | `/health` | Health check. |
| `GET` | `/ready` | Readiness check. |

## LLMRequest

```json
{
  "tenant_id": "default",
  "agent_id": "telecom_contas",
  "profile": "judge",
  "component": "judge",
  "operation": "chat_completion",
  "messages": [
    {"role": "system", "content": "Você é um avaliador."},
    {"role": "user", "content": "Avalie a resposta."}
  ],
  "parameters": {
    "temperature": 0,
    "max_tokens": 800
  },
  "metadata": {
    "request_id": "req-001",
    "trace_id": "trace-001",
    "session_id": "default:telecom_contas:session-001"
  }
}
```

## LLMResponse

```json
{
  "provider": "oci_openai",
  "model": "openai.gpt-4.1",
  "profile": "judge",
  "content": "Resultado da geração.",
  "usage": {
    "input_tokens": 1200,
    "output_tokens": 300,
    "total_tokens": 1500
  },
  "latency_ms": 820,
  "finish_reason": "stop",
  "metadata": {
    "fallback_used": false
  }
}
```

## Profiles

```yaml
profiles:
  default:
    provider: oci_openai
    model: openai.gpt-4.1
    temperature: 0.2
    max_tokens: 2048

  supervisor:
    provider: oci_openai
    model: openai.gpt-4.1
    temperature: 0
    max_tokens: 700

  router:
    provider: oci_openai
    model: openai.gpt-4.1
    temperature: 0
    max_tokens: 500

  guardrail:
    provider: oci_openai
    model: openai.gpt-4.1
    temperature: 0
    max_tokens: 600

  judge:
    provider: oci_openai
    model: openai.gpt-4.1
    temperature: 0
    max_tokens: 800

  rag_generation:
    provider: oci_openai
    model: openai.gpt-4.1
    temperature: 0.1
    max_tokens: 1800
```

## Providers

| Provider | Autenticação | Uso |
|---|---|---|
| `mock` | Nenhuma | Testes locais. |
| `oci_openai` | API Key / endpoint compatible | OCI GenAI OpenAI-Compatible. |
| `oci_sdk` | OCI Auth Mode | SDK nativo OCI. |
| `openai_compatible` | API Key | Endpoint compatível OpenAI. |

## OCI Authentication

| Variável | Valores |
|---|---|
| `LLM_PROVIDER` | `mock`, `oci_openai`, `oci_sdk`, `openai_compatible` |
| `OCI_AUTH_MODE` | `config_file`, `instance_principal`, `resource_principal`, `workload_identity` |
| `OCI_GENAI_API_KEY` | API key para provider compatível |

## Fallback

```yaml
fallback:
  enabled: true
  policies:
    default:
      chain:
        - profile: default
        - profile: default_low_cost
    judge:
      enabled: false
```

## Rate Limit

```yaml
rate_limits:
  default:
    requests_per_minute: 600
    tokens_per_minute: 1000000
  agents:
    telecom_contas:
      requests_per_minute: 120
```

## Eventos

| Evento | Descrição |
|---|---|
| `ai.request.received` | Requisição recebida. |
| `ai.profile.resolved` | Profile resolvido. |
| `ai.provider.selected` | Provider selecionado. |
| `ai.completion.started` | Chamada iniciada. |
| `ai.completion.completed` | Chamada concluída. |
| `ai.fallback.used` | Fallback utilizado. |
| `ai.request.failed` | Falha de inferência. |

## Métricas

| Métrica | Dimensões |
|---|---|
| `ai_requests_total` | provider, model, profile, tenant, agent, status |
| `ai_latency_ms` | provider, model, profile |
| `ai_tokens_total` | provider, model, input/output |
| `ai_cost_estimated` | provider, model, tenant, agent |
| `ai_fallback_total` | source_profile, fallback_profile |

## Segurança

- API keys não são gravadas em logs.
- Prompts podem ser mascarados conforme política.
- Providers são autorizados por tenant.
- Workload Identity é usada em Kubernetes quando configurada.
- Modelos bloqueados por política retornam erro controlado.


## Requisitos Não Funcionais

| Categoria | Requisito |
|---|---|
| Disponibilidade | Componentes deployáveis expõem `/health` e `/ready`. |
| Escalabilidade | Apps stateless escalam horizontalmente. Estado conversacional fica em repositórios externos. |
| Segurança | Segredos são fornecidos por secret store ou Kubernetes Secrets. |
| Observabilidade | Logs, métricas e traces usam correlação por request_id, trace_id, session_id, tenant_id e agent_id. |
| Auditabilidade | Decisões de rota, guardrail, judge, MCP e LLM são rastreáveis. |
| Portabilidade | Execução suportada em local, Docker Compose e Kubernetes/OKE. |
| Configuração | Comportamento variável é controlado por `.env` e YAML versionado. |


## Critérios de Aceite

- [ ] Endpoint de chat completion aceita LLMRequest.
- [ ] Endpoint de embeddings aceita EmbeddingRequest.
- [ ] Profiles são resolvidos por `llm_profiles.yaml`.
- [ ] Provider/model/profile aparecem em logs e traces.
- [ ] Fallback é explícito e rastreável.
- [ ] Rate limit é aplicado por tenant/agente.
- [ ] OCI Auth funciona por ambiente.
- [ ] Modelo não autorizado é rejeitado.
- [ ] Uso de tokens é registrado.
- [ ] Erros retornam payload padronizado.


## Glossário

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
