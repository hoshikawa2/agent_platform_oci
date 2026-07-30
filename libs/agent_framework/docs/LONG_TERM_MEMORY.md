# Long-Term Memory

Capacidade nativa do `agent_framework`, isolada por `tenant_id + agent_id + customer_key`.

O runtime carrega e injeta as memórias automaticamente. Os dois templates persistem os fatos após `supervisor_review`. Os agentes individuais não precisam de alteração.

## Teste

```bash
PYTHONPATH=libs/agent_framework/src python templates/agent_template_backend/scripts/test_long_term_memory.py
```
