# Offline Workflow Regression

O backend de produção de `WorkflowRuntime` continua sendo **LangGraph**. A ausência do pacote `langgraph` em produção é erro de configuração.

Para builders restritos/offline, o runtime aceita `allow_deterministic_fallback=True`. Esse modo é deliberadamente opt-in e existe somente para exercitar a DSL do framework (actions, edges, condições, pause/resume e trace) de forma reproduzível em testes offline/regressão. Quando `allow_deterministic_fallback=True`, o backend determinístico é selecionado explicitamente mesmo que LangGraph esteja instalado. Ele nunca é selecionado automaticamente em produção.

Exemplo de teste:

```python
runtime = WorkflowRuntime(
    repository,
    actions=registry,
    allow_deterministic_fallback=True,
)
first = await runtime.arun("workflow", payload)
assert first.status == "PAUSED"
final = await runtime.aresume("workflow", first.execution_id, {"resposta": "SIM"})
assert final.status == "COMPLETED"
```

O objetivo é não transformar indisponibilidade de rede/PyPI em `pytest.skip`, sem mascarar o requisito de LangGraph do runtime de produção.
