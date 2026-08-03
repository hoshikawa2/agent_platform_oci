# Como usar o `agent_template_backend_day_zero`

Este template é uma cópia do backend completo, mas com a lógica dos agentes de exemplo comentada.

## Fluxo mantido

```text
Gateway / Canal
  -> AgentWorkflow
  -> Input Guardrails
  -> Router / Supervisor Router
  -> Agente
  -> OutputSupervisor
  -> Output Guardrails
  -> Judges
  -> Persistência
```

## Onde escrever código

O ponto principal é o método `run()` dos agentes em `app/agents/`.

A estrutura esperada pelo workflow é:

```python
async def run(self, state):
    ...
    return {
        "answer": answer,
        "next_state": "MEU_ESTADO"
    }
```

## Como usar MCP

Dentro de `run()`:

```python
tool_context = await self._collect_tool_context(state)
```

## Como usar RAG

Dentro de `run()`:

```python
rag_context, rag_metadata = await self._retrieve_rag_context(state)
```

## Como chamar o LLM com cache/telemetria

```python
answer = await self._invoke_llm_cached(state, "MeuAgente", messages)
```

## Como ajustar roteamento

Edite `config/routing.yaml`.

O arquivo original foi mantido para servir de referência, mas as intents devem ser adaptadas para o domínio do novo agente.
