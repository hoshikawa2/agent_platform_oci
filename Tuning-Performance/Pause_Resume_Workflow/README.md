# Pause/Resume Workflow — LangGraph encapsulado pelo Agent Framework OCI

Este exemplo demonstra uma capability genérica do `agent_framework_oci`: workflows determinísticos podem interromper a execução para obter uma resposta do cliente e retomar posteriormente pelo mesmo `execution_id`, sem que o domínio importe ou monte um `StateGraph`.

## Conceito

A aplicação declara o workflow em YAML. `WorkflowRuntime` transforma a definição em LangGraph internamente, utiliza o checkpointer configurado pelo framework e expõe somente:

- `arun(name, payload)` — inicia ou executa o workflow;
- `aresume(name, execution_id, value)` — retoma o workflow pausado;
- `WorkflowRunResult.status` — `PAUSED`, `COMPLETED` ou `FAILED`.

O `pause` é compilado em um nó separado da action anterior. Isto impede que uma action com efeito colateral seja executada novamente quando o cliente responde.

## Executar

A partir da raiz do exemplo, com as dependências do framework instaladas:

```bash
python -m app.demo
pytest -q
```

## YAML

`workflows/confirmacao.v1.yaml` mostra `expected_input`, normalização, valores permitidos e `resume_from`.

## Persistência

O exemplo usa `MemorySaver` apenas para ser autocontido. Em aplicações reais use `create_langgraph_checkpointer(settings)`. Assim `execution_id` é o `thread_id` do LangGraph e a retomada sobrevive a processos/replicas conforme o provider configurado (por exemplo Autonomous Database).

## Regra arquitetural

Código de domínio não deve importar `langgraph.graph.StateGraph`. Para grafos de agentes use `FrameworkStateGraph`; para workflows determinísticos de negócio use `WorkflowRuntime`.
