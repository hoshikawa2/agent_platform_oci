# Deterministic Transactional Workflow

Esta variante contém um `agent_template_backend` funcional que conecta o fluxo
conversacional do framework ao motor determinístico de workflows transacionais.

## Por que este nome

`Deterministic_Transactional_Workflow` é mais preciso que apenas
`Transactional_Workflow`: a confirmação transacional já existia. O diferencial
desta variante é executar uma sequência multi-etapas por um grafo determinístico,
em vez de deixar o LLM escolher cada etapa.

## Fluxo demonstrado

1. O router seleciona `orders_agent`.
2. O runtime coleta `order_id` e `reason` por clarification.
3. O framework solicita confirmação.
4. Após uma confirmação explícita, a policy de `solicitar_devolucao` seleciona
   `execution.mode: workflow`.
5. O `WorkflowToolExecutor` carrega `devolucao_pedido.active.yaml`.
6. O LangGraph executa `validar_pedido` e `registrar_devolucao`.
7. O agente responde com protocolo e `workflow_execution_id`.

## Executar

```bash
cd Tuning-Performance/Deterministic_Transactional_Workflow/agent_template_backend
pip install -e ../../../libs/agent_framework
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Frases de teste

```text
Quero devolver o pedido 123 porque me arrependi da compra.
```

Depois:

```text
Sim, confirmo.
```

Resultado esperado: protocolo `DEV-123`, status `REQUESTED` e um
`workflow_execution_id`.

Clarification em turnos separados:

```text
Quero devolver uma compra.
O pedido é o 123.
Eu me arrependi da compra.
Sim, confirmo.
```

Cancelamento:

```text
Quero devolver o pedido 123 porque veio diferente do anunciado.
Não, cancele.
```

Nesse caso o workflow não deve iniciar.

## Configuração principal

- `.env`: `ENABLE_TRANSACTIONAL_WORKFLOWS=true`
- `.env`: `WORKFLOWS_PATH=./workflows`
- `config/tool_policies.yaml`: associa `solicitar_devolucao` ao workflow.
- `workflows/devolucao_pedido.active.yaml`: define a versão ativa.
- `app/workflow_actions/devolucao.py`: contém as actions do domínio.
- `app/agents/runtime.py`: integração do executor com o fluxo conversacional.

## Evidências

Procure os eventos:

- `IC.TRANSACTIONAL_WORKFLOW_STARTED`
- `IC.TRANSACTIONAL_WORKFLOW_COMPLETED`
- `IC.TRANSACTIONAL_WORKFLOW_FAILED`

O resultado também contém:

- `execution_mode=workflow`
- `workflow_name`
- `workflow_version`
- `workflow_execution_id`
