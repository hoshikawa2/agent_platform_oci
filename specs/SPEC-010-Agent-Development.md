# SPEC-010 — Agent Development

## Escopo

Esta SPEC define o padrão para criação de agentes usando templates, configuração YAML, BusinessContext, MCP, guardrails, judges, RAG, memória, observabilidade e evals.

## Estrutura do Template

```text
templates/backend/
├── app/
│   ├── main.py
│   ├── state.py
│   ├── workflows/
│   │   └── agent_graph.py
│   ├── agents/
│   │   ├── runtime.py
│   │   └── domain_agent.py
│   └── examples/
├── config/
│   ├── agents.yaml
│   ├── routing.yaml
│   ├── tools.yaml
│   ├── mcp_servers.yaml
│   ├── mcp_parameter_mapping.yaml
│   ├── identity.yaml
│   ├── guardrails.yaml
│   ├── judges.yaml
│   ├── prompt_policy.yaml
│   └── agents/<agent_id>/
├── Dockerfile
├── requirements.txt
└── .env.example
```

## Responsabilidades do Framework

- LangGraph;
- memória;
- checkpoint;
- sessão;
- router;
- supervisor;
- guardrails;
- judges;
- telemetry;
- MCP integration;
- RAG genérico;
- cache;
- providers LLM;
- event bus.

## Responsabilidades do Agente

- prompts de domínio;
- regras de negócio;
- schemas específicos;
- decisão de uso de evidências;
- tratamento de campos obrigatórios;
- mensagens de domínio;
- ICs de jornada;
- datasets de eval específicos.

## Registro do Agente

```yaml
agents:
  financeiro_agent:
    enabled: true
    description: "Agente financeiro"
    profile: financeiro_agent
    rag_namespace: financeiro
    allowed_tools:
      - consultar_fatura
      - consultar_pagamentos
```

## Roteamento

```yaml
intents:
  financeiro_consulta_fatura:
    route: financeiro_agent
    keywords:
      - fatura
      - boleto
      - cobrança
    mcp_tools:
      - consultar_fatura
```

## Tool Mapping

```yaml
tools:
  consultar_fatura:
    map:
      customer_key: msisdn
      contract_key: invoice_id
      interaction_key: ura_call_id
      session_key: session_id
```

## Classe de Agente

```python
class FinanceiroAgent(AgentRuntimeMixin):
    name = "financeiro_agent"

    def __init__(
        self,
        llm,
        telemetry=None,
        tool_router=None,
        rag_service=None,
        cache=None,
        settings=None,
        observer=None,
        memory=None,
        summary_memory=None,
    ):
        self.llm = llm
        self.telemetry = telemetry
        self.tool_router = tool_router
        self.rag_service = rag_service
        self.cache = cache
        self.settings = settings
        self.observer = observer
        self.memory = memory
        self.summary_memory = summary_memory

    async def run(self, state):
        await self._emit_ic("IC.FINANCEIRO_AGENT_STARTED", state, {})
        tool_context = await self._collect_mcp_context(state)
        rag_context, rag_metadata = await self._retrieve_rag_context(state)
        response = await self._invoke_llm_cached(
            state,
            "FinanceiroAgent",
            [
                {"role": "system", "content": "Você é um agente financeiro."},
                {"role": "user", "content": state.get("sanitized_input") or state.get("user_text", "")},
            ],
        )
        await self._emit_ic("IC.FINANCEIRO_AGENT_COMPLETED", state, {})
        return {
            "response_text": response,
            "mcp_results": tool_context,
            "rag_metadata": rag_metadata,
        }
```

## Ordem de Confiança dos Dados

1. `tool_arguments`
2. `business_context`
3. `context`
4. `session.metadata`
5. `state`
6. extração complementar do texto

## Prompt Policy

```yaml
prompt_policy:
  system_prompt_path: prompts/system.md
  response_style: concise
  require_evidence: true
  allow_tool_usage: true
```

## Guardrails por Agente

```yaml
input:
  - code: FIN_INPUT_POLICY
    enabled: true
    mode: observe

output:
  - code: FIN_OUTPUT_COMPLIANCE
    enabled: true
    mode: enforce
```

## Judges por Agente

```yaml
judges:
  - name: response_quality
    enabled: true
    threshold: 0.75
  - name: groundedness
    enabled: true
    threshold: 0.70
```

## Dataset de Eval

```yaml
dataset:
  name: financeiro_agent_regression
  version: 1.0.0
  items:
    - id: fin-001
      input: "Quero consultar minha fatura"
      business_context:
        customer_key: "11999999999"
        contract_key: "3000131180"
      expected:
        route: financeiro_agent
        tools:
          - consultar_fatura
        min_scores:
          quality: 0.75
          groundedness: 0.70
```

## Testes

| Teste | Escopo |
|---|---|
| Unitário | Classe do agente. |
| Routing | Intent e rota. |
| MCP Mapping | BusinessContext para argumentos. |
| Guardrails | Entrada e saída. |
| Judges | Scores mínimos. |
| Runtime | Execução completa. |
| Memory | Continuidade de conversa. |
| Checkpoint | Resume/replay. |
| Observability | Trace e eventos. |
| Certification | Evidências finais. |

## Definition of Done

- agente registrado;
- rota configurada;
- tools declaradas;
- mapping definido;
- prompts versionados;
- guardrails configurados;
- judges configurados;
- dataset criado;
- testes executados;
- traces gerados;
- certification suite aprovada;
- documentação do agente atualizada.

## Anti-patterns

- agente criando sessão;
- agente abrindo SSE;
- agente compilando LangGraph;
- agente chamando sistema externo diretamente;
- prompt hardcoded sem política;
- lógica genérica duplicada no agente;
- payload bruto de canal dentro do agente;
- ausência de dataset de eval.


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

- [ ] Novo agente é criado sem alterar core do framework.
- [ ] Configuração ocorre por YAML e `.env`.
- [ ] Agente usa BusinessContext.
- [ ] Agente acessa MCP por router/gateway.
- [ ] Agente não conhece payload bruto de canal.
- [ ] Guardrails e judges são configurados.
- [ ] Dataset de eval existe.
- [ ] Testes mínimos executam.
- [ ] Trace completo é gerado.
- [ ] Definition of Done é atendida.


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
