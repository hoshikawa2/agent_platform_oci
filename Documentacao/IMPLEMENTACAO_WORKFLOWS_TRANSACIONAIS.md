# Implementação — workflows transacionais determinísticos

## Entrega

Foi adicionada ao `agent_framework_oci` uma capacidade opcional para executar transações multi-etapas como workflows determinísticos compilados em LangGraph.

### Módulo novo

`libs/agent_framework/src/agent_framework/workflows/`

- `models.py`: contratos Pydantic e validação estrutural;
- `repository.py`: resolução de versão ativa e leitura de YAML imutável;
- `registry.py`: registro desacoplado de actions sync/async;
- `runtime.py`: compilação, cache e execução do StateGraph;
- `tool_executor.py`: integração com a política da tool;
- `__init__.py`: API pública.

### Política expandida

`ToolPolicy` agora aceita:

```yaml
execution:
  mode: direct_tool | workflow | agent
  workflow: nome_do_workflow
  version: active | 1
```

O default permanece `direct_tool`, preservando compatibilidade.

### Configuração

Foram adicionados:

- `ENABLE_TRANSACTIONAL_WORKFLOWS=false`;
- `WORKFLOWS_PATH=./workflows`.

### Template

Inclui um exemplo completo de devolução de pedido com:

- confirmação e campos obrigatórios pela política;
- workflow YAML versionado;
- actions de domínio no backend;
- bifurcação determinística baseada no resultado da validação.

## Validação realizada

- `tests/unit/test_tool_policies.py`: 4 testes aprovados;
- compilação Python de framework, template e novos testes: aprovada;
- o teste funcional novo do LangGraph foi criado, mas não pôde ser executado neste container porque `langgraph` não está instalado no ambiente. A dependência já está declarada no `pyproject.toml` do framework.

## Escopo e segurança

Esta entrega cria o motor e a integração de política. Para operações críticas em produção ainda é necessário conectar:

- execution store persistente;
- idempotência de negócio nas actions/APIs;
- autorização por escopo;
- telemetria IC/NOC específica de workflow;
- compensação/Saga quando aplicável;
- estratégia corporativa de timeout e retry.

Esses itens foram explicitamente documentados para evitar a falsa impressão de que retry por si só garante segurança transacional.
