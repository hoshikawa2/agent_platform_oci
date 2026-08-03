# Como usar IC, NOC e GRL no Template Backend

## IC — Item de Controle

Use IC para registrar eventos de negócio relevantes.

```python
await observer.emit_ic(
    "IC.FATURA_CONSULTADA",
    {"session_id": session_id, "invoice_id": invoice_id},
    component="billing_agent",
)
```

## NOC — Evento operacional

Use NOC para saúde técnica, latência, erros e checkpoints operacionais.

```python
await observer.emit_noc(
    "003",
    {"session_id": session_id, "resourceName": "ADB", "latencyMs": 120},
    component="repository",
)
```

## GRL — Evento de guardrail

Normalmente o framework emite GRL automaticamente. Use manualmente apenas para
rails customizados dentro do agente.

```python
await observer.emit_grl(
    "OBSERVE",
    {"session_id": session_id, "rail_code": "CUSTOM_POLICY"},
    component="custom_rail",
)
```

## Onde já existe no template

- `app/workflows/agent_graph.py` emite IC/NOC no ciclo do workflow.
- `app/agents/runtime.py` emite IC para MCP/tools.
- `app/agents/*_agent.py` contém exemplos dentro do método `run()`.
- `app/examples/` contém exemplos isolados.
