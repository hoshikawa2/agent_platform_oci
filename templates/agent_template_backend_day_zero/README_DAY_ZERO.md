# agent_template_backend_day_zero

Este folder é uma cópia do `agent_template_backend`, porém transformada em um template **Day Zero**.

A ideia é o desenvolvedor começar um agente novo sem apagar manualmente exemplos de negócio.

## O que foi mantido

Foi mantida a estrutura original do backend:

- `app/main.py`
- `app/workflows/agent_graph.py`
- `app/state.py`
- `app/agents/runtime.py`
- `app/agents/prompting.py`
- configurações em `config/`
- integração com `agent_framework`
- Analytics / Observer
- NOC / GRL
- OutputSupervisor
- MCP Router
- RAG
- cache
- memória
- checkpoints
- Langfuse / OTEL

## O que foi comentado

As implementações de exemplo dos agentes foram comentadas nos arquivos:

- `app/agents/billing_agent.py`
- `app/agents/product_agent.py`
- `app/agents/orders_agent.py`
- `app/agents/support_agent.py`

Cada arquivo contém:

1. um esqueleto funcional mínimo;
2. comentários `TODO` para o desenvolvedor;
3. a implementação original comentada no final do arquivo.

## Como desenvolver um novo agente

1. Escolha qual classe vai reutilizar inicialmente, por exemplo `BillingAgent`.
2. Edite o método `run()`.
3. Ajuste o prompt em `apply_agent_profile_prompt(...)`.
4. Descomente MCP se precisar de tools:

```python
# tool_context = await self._collect_tool_context(state)
```

5. Descomente RAG se precisar de base de conhecimento:

```python
# rag_context, rag_metadata = await self._retrieve_rag_context(state)
```

6. Ajuste o retorno:

```python
return {
    "answer": answer,
    "next_state": "MEU_ESTADO",
}
```

## O que o desenvolvedor normalmente altera

- `app/agents/*.py`
- `config/routing.yaml`
- `config/agents.yaml`
- `config/tools.yaml`
- `config/mcp_servers.yaml`
- `config/mcp_parameter_mapping.yaml`
- `.env`

## O que normalmente não deve ser alterado no início

- `app/main.py`
- `app/workflows/agent_graph.py`
- `app/state.py`
- `app/agents/runtime.py`

Esses arquivos são o esqueleto de execução usando o framework.
