# Guardrails paralelos fail-fast e Observer IC

## O que foi implementado

### 1. ParallelRailExecutor

Arquivo principal:

```text
agent_framework/src/agent_framework/guardrails/parallel_executor.py
```

Também foi criado um alias de compatibilidade:

```text
agent_framework/src/agent_framework/guardrails/executor.py
```

Esse alias evita erro quando algum código antigo importar:

```python
from agent_framework.guardrails.executor import ParallelRailExecutor
```

### 2. Execução paralela no GuardrailPipeline

Arquivo alterado:

```text
agent_framework/src/agent_framework/guardrails/pipeline.py
```

O pipeline continua retornando o contrato antigo:

```python
(texto_final, list[RailDecision])
```

mas internamente pode executar rails em paralelo com fail-fast.

### 3. Execução paralela no OutputSupervisor

Arquivo alterado:

```text
agent_framework/src/agent_framework/guardrails/output_supervisor.py
```

O `OutputSupervisor` agora usa `ParallelRailExecutor` quando habilitado.

### 4. Configuração

Novas configurações:

```env
ENABLE_PARALLEL_GUARDRAILS=true
GUARDRAILS_FAIL_FAST=true
```

Também foram adicionadas em:

```text
agent_framework/src/agent_framework/config/settings.py
.env
.env.example
agent_template_backend/.env
agent_template_backend_day_zero/.env
```

### 5. Observer IC

O `AgentObserver` já tinha `emit_ic()`.

Foi complementada a API global compatível com FIRST/TIM:

```python
from agent_framework.observer import ic, aic, noc, anoc, grl, agrl
```

Exemplos:

```python
ic("AGENT_COMPLETED", data={"session_id": "..."})
await aic("MCP_TOOL_CALLED", data={"tool_name": "consultar_fatura"})
```

### 6. ICs automáticos no template backend

O backend emite agora:

```text
IC.AGENT_STARTED
IC.ROUTE_SELECTED
IC.MCP_TOOL_CALLED
IC.TOOL_CALLED
IC.AGENT_COMPLETED
```

Além dos eventos já existentes:

```text
NOC.001
NOC.005
NOC.006
GRL.001 ... GRL.009
```

## Validações executadas

Foram executadas validações locais com `PYTHONPATH=agent_framework/src`:

```bash
python3 -m compileall -q agent_framework/src/agent_framework agent_template_backend/app agent_template_backend_day_zero/app
```

Smoke tests executados:

```text
1. Import de ParallelRailExecutor via agent_framework.guardrails
2. Import de ParallelRailExecutor via agent_framework.guardrails.executor
3. Execução fail-fast: FastBlock cancela SlowAllow
4. GuardrailPipeline paralelo retorna RailDecision legado
5. OutputSupervisor paralelo retorna RailAction.BLOCK
6. API global observer.ic/noc/grl/aic/anoc/agrl
```

Observação: o import completo do `agent_template_backend.app.workflows.agent_graph` depende de `langgraph`, que não está instalado no sandbox de validação. O arquivo foi validado por `compileall`, e a dependência já consta em `agent_template_backend/requirements.txt`.
