# SPEC-003 — Agent Gateway

## Escopo

O Agent Gateway é o ponto único de entrada da plataforma para canais e consumidores externos.

Sua responsabilidade é receber mensagens, gerenciar sessões globais, resolver o backend/agente responsável, executar roteamento, realizar handoff entre agentes/backends e encaminhar eventos SSE.

O Agent Gateway não executa inferência LLM nem embeddings. Essas capacidades pertencem ao Runtime e ao Agent Framework.

---

## Responsabilidades

### Entrada Única da Plataforma

```text
Web
WhatsApp
Voice
Teams
Slack
      |
      v
Agent Gateway
      |
      +--> Agent Backend A
      |
      +--> Agent Backend B
      |
      +--> Agent Backend C
```

### Gerenciamento de Sessões

Responsável por:

- Criação de sessões
- Recuperação de sessões
- Atualização de contexto global
- Persistência de metadados de sessão
- Correlação de requisições

Exemplo:

```json
{
  "session_id": "default:telecom_contas:123",
  "tenant_id": "default",
  "active_backend": "telecom_contas",
  "active_agent": "telecom_contas",
  "turn_count": 12,
  "metadata": {}
}
```

---

## Backend Routing

Resolve qual backend deve processar a mensagem.

Exemplo:

```yaml
backends:
  telecom_contas:
    url: http://backend-contas:8000

  telecom_ofertas:
    url: http://backend-ofertas:8000
```

Critérios possíveis:

- Backend padrão
- Regras YAML
- Intenção detectada
- Contexto da sessão
- Router LLM (opcional)

---

## Handoff

Permite transferência entre agentes ou backends.

Exemplo:

```text
Contas
   |
   +--> Ofertas
   |
   +--> Retenção
```

O handoff deve preservar:

- session_id
- conversation_key
- business context
- histórico da conversa
- metadados de correlação

---

## SSE Proxy

Responsável por encaminhar eventos de streaming para clientes.

### Endpoints

| Método | Endpoint |
|----------|----------|
| POST | /gateway/message |
| POST | /gateway/message/sse |
| GET | /gateway/events/{session_id} |

Eventos SSE suportados:

- connected
- workflow.started
- message.responded
- workflow.completed
- flow.end
- error

---

## Backend Discovery

Pode operar com catálogo estático ou descoberta dinâmica.

### Catálogo Estático

```yaml
backends:
  telecom_contas:
    url: http://contas:8000

  telecom_ofertas:
    url: http://ofertas:8000
```

### Descoberta Dinâmica

```yaml
service_discovery:
  enabled: true
```

Capacidades:

- Registro automático
- Health check periódico
- Atualização de catálogo
- Sincronização de metadados

---

## Health e Operação

### Endpoints

| Método | Endpoint |
|----------|----------|
| GET | /health |
| GET | /ready |
| GET | /backends |
| GET | /debug/sessions |

---

## Contrato GatewayRequest

```json
{
  "tenant_id": "default",
  "agent_id": "telecom_contas",
  "session_id": "default:telecom_contas:123",
  "message": "Quero consultar minha fatura",
  "business_context": {
    "customer_key": "11999999999"
  },
  "metadata": {
    "request_id": "req-001",
    "trace_id": "trace-001"
  }
}
```

---

## Contrato GatewayResponse

```json
{
  "session_id": "default:telecom_contas:123",
  "backend": "telecom_contas",
  "agent": "telecom_contas",
  "message": "Sua fatura está disponível.",
  "metadata": {
    "request_id": "req-001"
  }
}
```

---

## Eventos

| Evento | Descrição |
|----------|----------|
| agent.gateway.request.received | Requisição recebida |
| agent.gateway.session.created | Sessão criada |
| agent.gateway.backend.selected | Backend selecionado |
| agent.gateway.handoff.started | Handoff iniciado |
| agent.gateway.handoff.completed | Handoff concluído |
| agent.gateway.sse.connected | Cliente SSE conectado |
| agent.gateway.request.failed | Falha de processamento |

---

## Métricas

| Métrica | Dimensões |
|----------|----------|
| gateway_requests_total | tenant, backend, agent, status |
| gateway_sessions_active | tenant |
| gateway_backend_selection_total | backend |
| gateway_handoff_total | origem, destino |
| gateway_latency_ms | backend |
| gateway_sse_connections | backend |

---

## Segurança

- Autenticação obrigatória quando configurada.
- Propagação de identidade entre gateways.
- Máscara de dados sensíveis em logs.
- Correlação por request_id, trace_id e session_id.
- Controle de acesso por tenant.

---

## Requisitos Não Funcionais

| Categoria | Requisito |
|----------|----------|
| Disponibilidade | Expor /health e /ready |
| Escalabilidade | Stateless com escala horizontal |
| Observabilidade | Logs, métricas e traces |
| Auditabilidade | Todas as decisões de roteamento rastreáveis |
| Segurança | Segredos externos e mascaramento |
| Portabilidade | Local, Docker e Kubernetes |
| Configuração | YAML e variáveis de ambiente |

---

## Critérios de Aceite

- [ ] Recebe mensagens de múltiplos canais.
- [ ] Seleciona backend corretamente.
- [ ] Mantém sessão global.
- [ ] Encaminha SSE.
- [ ] Executa handoff.
- [ ] Preserva Business Context.
- [ ] Suporta múltiplos backends.
- [ ] Permite descoberta dinâmica.
- [ ] Expõe health e readiness.
- [ ] Gera métricas e telemetria.
