# SPEC-014 — Templates and Agent Creation Model

## Agent Platform OCI

Version: 1.0.0


---

## Padrão de leitura

Cada SPEC está organizada para servir tanto como contrato arquitetural quanto como guia prático de adoção.

A estrutura usada é:

1. Conceito.
2. Problema que resolve.
3. Quando usar.
4. Quando não usar.
5. Arquitetura.
6. Implementação.
7. Exemplos.
8. Erros comuns.
9. Critérios de aceite.

---


# 1. Conceito

Templates são scaffolds oficiais para criar agentes, MCP servers e backends compatíveis com a Agent Platform OCI.

Eles aceleram o início de um projeto, mas não substituem o framework. O template contém a estrutura mínima de aplicação e os pontos de extensão esperados.

# 2. Problema que resolve

Sem template:

- cada squad cria estrutura diferente;
- imports e configs variam;
- MCP mapping é esquecido;
- datasets não são criados;
- guardrails e judges ficam ausentes;
- deploy não segue padrão;
- onboarding demora.

# 3. Templates oficiais

| Template | Uso |
| --- | --- |
| backend | Criação de agentes com runtime. |
| backend_day_zero | Bootstrap acelerado com exemplos. |
| mcp_server | Criação de MCP server. |
| channel_adapter | Adapter de canal quando aplicável. |


# 4. Estrutura padrão de agente

```text
my_agent/
├── app/
│   ├── main.py
│   ├── state.py
│   ├── workflows/
│   │   └── agent_graph.py
│   └── agents/
│       └── my_agent.py
├── config/
│   ├── agents.yaml
│   ├── routing.yaml
│   ├── tools.yaml
│   ├── mcp_servers.yaml
│   ├── mcp_parameter_mapping.yaml
│   ├── guardrails.yaml
│   ├── judges.yaml
│   └── llm_profiles.yaml
├── prompts/
├── datasets/
├── tests/
├── Dockerfile
└── README.md
```

# 5. O que fica no framework

- LangGraph runtime;
- sessão;
- memória;
- checkpoint;
- guardrails genéricos;
- judges genéricos;
- MCP client/router;
- RAG genérico;
- telemetry;
- providers;
- event bus.

# 6. O que fica no agente

- prompts;
- regras de negócio;
- intents;
- tools específicas;
- datasets;
- testes;
- guardrails de domínio;
- judges de domínio.

# 7. Passo a passo para criar agente do zero

## Passo 1 — Copiar template

```bash
cp -R templates/backend financeiro_agent
cd financeiro_agent
```

## Passo 2 — Definir escopo

```text
Agente: financeiro_agent
Objetivo: responder dúvidas sobre faturas, pagamentos e cobranças.
Fora de escopo: vendas, cancelamento e suporte técnico.
```

## Passo 3 — Registrar agente

```yaml
agents:
  financeiro_agent:
    enabled: true
    description: "Agente financeiro"
    rag_namespace: financeiro
    allowed_tools:
      - consultar_fatura
      - consultar_pagamentos
```

## Passo 4 — Configurar rotas

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

## Passo 5 — Configurar tools

```yaml
tools:
  consultar_fatura:
    server: telecom
    enabled: true
    idempotent: true
    cache_ttl_seconds: 300
```

## Passo 6 — Mapear BusinessContext

```yaml
tools:
  consultar_fatura:
    map:
      customer_key: msisdn
      contract_key: invoice_id
      session_key: session_id
```

## Passo 7 — Criar prompt

```text
Você é um agente financeiro.
Use MCP como fonte transacional.
Use RAG para políticas e procedimentos.
Não invente valores, datas ou status.
```

## Passo 8 — Implementar agente

```python
class FinanceiroAgent(AgentRuntimeMixin):
    name = "financeiro_agent"

    async def run(self, state):
        mcp = await self._collect_mcp_context(state)
        rag, rag_metadata = await self._retrieve_rag_context(state)
        answer = await self._invoke_llm_cached(
            state,
            "FinanceiroAgent",
            [
                {"role": "system", "content": "Você é um agente financeiro."},
                {"role": "user", "content": state.get("sanitized_input") or ""},
            ],
        )
        return {"response_text": answer, "mcp_results": mcp, "rag_metadata": rag_metadata}
```

## Passo 9 — Criar dataset

```yaml
dataset:
  name: financeiro_agent_regression
  version: 1.0.0
  items:
    - id: fin-001
      input: "Quero consultar minha fatura"
      expected:
        route: financeiro_agent
        tools:
          - consultar_fatura
```

## Passo 10 — Testar

```bash
pytest
af-evaluator run --agent-id financeiro_agent
af-certification run --agent-id financeiro_agent
```

# 8. Erros comuns

| Erro | Impacto | Correção |
| --- | --- | --- |
| Alterar o core para regra de domínio | Dificulta reuso. | Criar agente/config. |
| Esquecer dataset | Sem regressão. | Criar dataset mínimo. |
| Tool sem mapping | Argumentos ausentes. | Configurar mcp_parameter_mapping.yaml. |
| Prompt hardcoded | Sem governança. | Usar prompt_policy/prompts. |


# 9. Critérios de aceite

- [ ] Template usado como base.
- [ ] Agente registrado.
- [ ] Rotas configuradas.
- [ ] Tools configuradas.
- [ ] MCP mapping configurado.
- [ ] Prompt criado.
- [ ] Dataset criado.
- [ ] Testes executados.
- [ ] Evaluator executado.
- [ ] Certification aprovada.
