
### Workflows Transacionais e Estado

### Como usar este manual

Este é um **manual de referência especializado**. Ele não substitui o tutorial principal.

- Para criar um agente do início ao fim, use [`README.md`](../../../README.md).
- Use este documento quando precisar implementar, aprofundar ou diagnosticar **estado transacional, coleta de parâmetros, confirmação, pausa/retomada e evidência operacional**.
- Os exemplos históricos consolidados aqui devem ser lidos à luz da API atual do framework.
- Em caso de divergência, o código da versão e o `README.md` atual prevalecem.

### Relação com o tutorial principal

O `README.md` apresenta essa capacidade no fluxo normal de desenvolvimento. Este manual reúne detalhes que estavam distribuídos em `docs/`, `Documentacao/`, release notes, validações e guias especializados.

O objetivo aqui é responder **“como essa feature funciona em profundidade e como eu resolvo problemas nela?”**, sem transformar este arquivo em uma segunda cópia do tutorial principal.

### Escopo

Estado transacional, coleta de parâmetros, confirmação, pausa/retomada e evidência operacional.

### Conteúdo técnico consolidado

### Workflows Transacionais, Estado Multi-turno e Retomada

Guia de implementação para operações multi-etapas, fonte canônica do estado transacional, confirmação, merge de parâmetros, pausa/retomada, evidência operacional e interação com roteamento.

### Como usar este documento

Este é o documento consolidado de desenvolvimento para este assunto. Ele reúne arquitetura, configuração, exemplos, comportamento de runtime, compatibilidade, testes e troubleshooting que antes estavam distribuídos em vários arquivos. As seções de origem foram preservadas quando traziam detalhes técnicos distintos; notas de release foram incorporadas como comportamento atual ou histórico de correção.

### Guia de estado transacional multi-turno

> Conteúdo consolidado a partir de `docs/TRANSACTION_STATE_DEVELOPER_GUIDE.md`.

Este documento define o contrato operacional para transações multi-turno no Agent Framework OCI. Ele é normativo para hosts e templates que utilizam `AgentRuntime`, checkpoint LangGraph e tools transacionais.

### 1. Objetivo

Uma transação pode atravessar vários turnos. Exemplo:

```text
Usuário: quero cancelar o pedido
Framework: informe o número do pedido
Usuário: PED-1001
Framework: confirma o cancelamento?
Usuário: sim
Framework: executa a tool
```

O framework precisa preservar a transação entre todos esses turnos sem depender de reclassificação por LLM, keyword routing ou reextração de parâmetros já obtidos.

### 2. Fonte canônica do estado transacional

O estado canônico da transação em andamento é `active_transaction`.

```python
active_transaction: dict[str, Any]
last_transaction: dict[str, Any]
```

Todo `AgentState` usado por um host que habilita transações multi-turno **DEVE** declarar os dois campos. Como o LangGraph usa o schema do state para persistência/checkpoint, um campo criado apenas dinamicamente pelo runtime não é um contrato durável seguro.

Exemplo mínimo:

```python
from typing import Any, TypedDict

class AgentState(TypedDict, total=False):
    # ...campos normais...
    selected_tool_call: dict[str, Any]
    pending_tool_call: dict[str, Any]
    active_transaction: dict[str, Any]
    last_transaction: dict[str, Any]
    transaction_status: str
    missing_parameters: list[str]
    confirmation_required: bool
    confirmation_received: bool
```

### 3. Papel de cada campo

| Campo | Papel | Regra |
|---|---|---|
| `active_transaction` | Fonte canônica da transação ativa | Deve sobreviver a checkpoint/resume enquanto a transação estiver ativa. |
| `last_transaction` | Snapshot da última transação terminal | Usado para auditoria, evidência e continuidade controlada; não reativa automaticamente a transação. |
| `transaction_status` | Estado lógico atual | Ex.: `COLLECTING_PARAMETERS`, `AWAITING_CONFIRMATION`, `COMPLETED`, `CANCELLED`, `OUT_OF_SCOPE`. |
| `missing_parameters` | Parâmetros ainda necessários | Deve refletir o estado canônico da transação, não apenas a mensagem corrente. |
| `selected_tool_call` | Estado auxiliar/compatibilidade | Não deve substituir `active_transaction` como fonte canônica. |
| `pending_tool_call` | Estado auxiliar/compatibilidade | Pode ser usado por compatibilidade, mas não como latch principal. |
| `next_state` | Orientação de roteamento do workflow | Ajuda a manter o nó/agente correto durante coleta/confirmação. |
| `transaction_pre_validation` | Evidência de pré-validação | Mantém resultado de validação antes da confirmação/execução. |
| `transaction_evidence` | Evidências da execução | Mantém resultados e trilha de execução da transação. |

### 4. Ciclo de vida recomendado

```text
IDLE
  ↓ intenção transacional
COLLECTING_PARAMETERS
  ↓ parâmetros completos
PRE_VALIDATION (quando configurado)
  ↓ elegível
AWAITING_CONFIRMATION
  ↓ confirmação positiva
EXECUTING
  ↓
COMPLETED
```

Saídas terminais alternativas:

```text
CANCELLED
OUT_OF_SCOPE
FAILED
```

O runtime pode representar algumas fases internamente sem um `transaction_status` público separado. O requisito é preservar o latch e não perder argumentos já coletados.

### 5. Merge incremental de parâmetros

Uma resposta posterior deve complementar a transação existente, nunca recriá-la apenas a partir do texto atual.

```python
existing = dict((state.get("active_transaction") or {}).get("arguments") or {})
new_values = {"valor": "71.99"}
arguments = {**existing, **new_values}
```

Exemplo esperado:

```text
Turno 1: subject = "TIM CTRL Redes Sociais 8.0"
Turno 2: valor = "71.99"
Resultado: subject + valor permanecem disponíveis
```

### 6. Precedência de roteamento durante transação

Quando existe `active_transaction` em `COLLECTING_PARAMETERS`, a mensagem deve primeiro ser avaliada como possível resposta aos parâmetros pendentes.

Precedência normativa:

1. parâmetro pendente claramente preenchido → continuar a transação;
2. cancelamento/abandono explícito → cancelar a transação;
3. nova intenção inequívoca → interromper a transação e rotear;
4. keyword genérica do mesmo domínio/agente → **não** interromper a transação;
5. mensagem ambígua → manter a transação e clarificar.

Exemplos:

| Estado atual | Mensagem | Resultado correto |
|---|---|---|
| `retail_order_cancel`, falta `order_id` | `PED-1001` | Continua cancelamento e preenche `order_id`. |
| `retail_order_cancel`, falta `order_id` | `o pedido é o PED-1001` | Continua cancelamento; `pedido` não deve virar tracking. |
| contestação, falta `valor` | `R$ 71,99` | Continua contestação e preenche `valor`. |
| cancelamento pendente | `esquece, quero ver minha fatura` | Interrupção explícita permitida. |
| cancelamento pendente | `quero rastrear pedido` | Mudança inequívoca para tracking permitida. |

### 7. Checkpoint e retomada

Antes de executar roteamento normal, o host deve restaurar o checkpoint usando a mesma identidade de conversa (`tenant_id`, `agent_id`, `session_id`/`conversation_key` conforme contrato do host).

Após a restauração:

```text
active_transaction existe
       ↓
status ativo?
       ↓ sim
retomar a transação antes de keyword routing / continuity LLM
```

Um estado `COLLECTING_PARAMETERS` sem `active_transaction` deve ser tratado como inconsistência de estado e observado/diagnosticado; não deve silenciosamente reiniciar a tool a partir da mensagem corrente.

### 8. O que pertence ao framework e ao agente

Framework:

- persistência do latch;
- merge de argumentos;
- estados de coleta/confirmação;
- precedência de retomada;
- confirmação determinística;
- idempotência e evidência;
- checkpoint/resume.

Agente:

- definição das tools de domínio;
- parâmetros obrigatórios e mensagens de domínio;
- regras de elegibilidade específicas;
- pre-validation específica, quando houver;
- resposta final ao cliente.

O agente não deve implementar um segundo motor transacional paralelo ao `AgentRuntime`.

### 9. Checklist para novos hosts/templates

- [ ] `AgentState` declara `active_transaction`.
- [ ] `AgentState` declara `last_transaction`.
- [ ] `transaction_status` e `missing_parameters` fazem parte do state quando usados.
- [ ] O host usa checkpoint compatível com o schema do state.
- [ ] A mesma `conversation_key` é usada entre turnos da mesma conversa.
- [ ] Parâmetros já coletados são mesclados com novos valores.
- [ ] Respostas a parâmetros têm precedência sobre keyword routing genérico.
- [ ] Mudança explícita de intenção continua possível.
- [ ] O agente usa `transaction_state_patch(state)` ao retornar respostas transacionais quando o template o exige.
- [ ] Existem testes multi-turno para coleta, confirmação, interrupção e resume.

### 10. Testes regressivos mínimos

```text
A. cancelamento de pedido
1. "quero cancelar pedido"
2. "o pedido é o PED-1001"
Esperado: continua retail_order_cancel; não vira retail_order_tracking.

B. contestação
1. "não contratei TIM CTRL Redes Sociais 8.0"
2. "R$ 71,99"
Esperado: subject e valor chegam juntos à pre-validation.

C. interrupção explícita
1. iniciar transação e deixar parâmetro pendente
2. "esquece, quero ver minha fatura"
Esperado: transação é interrompida e nova intenção é roteada.

D. checkpoint/resume
1. iniciar transação
2. persistir/checkpoint
3. reconstruir execução usando a mesma conversation_key
4. fornecer o parâmetro faltante
Esperado: active_transaction é restaurado e concluído sem reiniciar a tool.
```

### 11. Anti-patterns

- reconstruir a transação somente a partir da última mensagem;
- usar `selected_tool_call` como única fonte do latch;
- remover `active_transaction` do `AgentState` por parecer redundante;
- permitir uma keyword genérica como `pedido` interromper coleta de `order_id`;
- armazenar parâmetros apenas em variáveis locais do nó;
- duplicar confirmação transacional no prompt do agente;
- limpar o latch antes do estado terminal.

### 12. Referências no projeto

- `specs/SPEC-002-Agent-Runtime.md`
- `specs/SPEC-010-Agent-Development.md`
- `templates/agent_template_backend/app/state.py`
- `libs/agent_framework/src/agent_framework/runtime/agent_runtime.py`
- `libs/agent_framework/src/agent_framework/routing/enterprise_router.py`
- `Tuning-Performance/Deterministic_Transactional_Workflow/`
- `Tuning-Performance/Transaction_Pre_Validation/`
- `Tuning-Performance/Transaction_Evidence/`

### Decisão arquitetural do motor de workflows

> Conteúdo consolidado a partir de `docs/ADR_TRANSACTIONAL_WORKFLOW_ENGINE.md`.

### Decisão

Adicionar ao framework uma capacidade opcional de execução determinística baseada em LangGraph. O motor é genérico; definições YAML e actions de domínio permanecem nos agentes.

### Razão

Operações multi-etapas com efeitos colaterais não devem depender do LLM para escolher a sequência crítica. A solução reduz tokens, latência e variação, além de melhorar auditoria, testes e versionamento.

### Compatibilidade

`execution.mode` assume `direct_tool`. Projetos existentes continuam usando MCP diretamente. A adoção de workflow é explícita por tool e pode ser controlada por `ENABLE_TRANSACTIONAL_WORKFLOWS`.

### Limites desta entrega

A base inclui validação, versionamento por arquivo, registry, execução sync/async, condições, retry por nó, cache de grafos e adapter de policy. Persistência corporativa de execution records, compensação/Saga, autorização por escopo e emissão de IC/NOC específica devem ser conectadas às abstrações existentes de cada deployment antes do uso em transações financeiras críticas.

### Implementação dos workflows determinísticos

> Conteúdo consolidado a partir de `Documentacao/IMPLEMENTACAO_WORKFLOWS_TRANSACIONAIS.md`.

### Entrega

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

### Validação realizada

- `tests/unit/test_tool_policies.py`: 4 testes aprovados;
- compilação Python de framework, template e novos testes: aprovada;
- o teste funcional novo do LangGraph foi criado, mas não pôde ser executado neste container porque `langgraph` não está instalado no ambiente. A dependência já está declarada no `pyproject.toml` do framework.

### Escopo e segurança

Esta entrega cria o motor e a integração de política. Para operações críticas em produção ainda é necessário conectar:

- execution store persistente;
- idempotência de negócio nas actions/APIs;
- autorização por escopo;
- telemetria IC/NOC específica de workflow;
- compensação/Saga quando aplicável;
- estratégia corporativa de timeout e retry.

Esses itens foram explicitamente documentados para evitar a falsa impressão de que retry por si só garante segurança transacional.

### Precedência da coleta de parâmetros

> Conteúdo consolidado a partir de `FIX_TRANSACTION_PARAMETER_PRECEDENCE.md`.

Esta correção remove a extração textual hardcoded de parâmetros transacionais e faz a coleta de `policy.requires` por um extrator LLM genérico.

### Regra de precedência

Enquanto existir uma transação ativa, o framework trata o turno nesta ordem:

```text
ACTIVE_TRANSACTION
       |
       +-- COLLECTING_PARAMETERS
       |      |
       |      +-- LLM tenta extrair SOMENTE os parâmetros ainda pendentes
       |      |
       |      +-- extraiu >= 1 ?
       |             |
       |             +-- SIM -> continua a transação; NÃO avalia intent_shift
       |             |
       |             +-- NÃO -> libera EnterpriseRouter para avaliar intent_shift
       |
       +-- AWAITING_CONFIRMATION
              |
              +-- reconhece confirmação/rejeição explícita
              |
              +-- reconheceu ?
                     |
                     +-- SIM -> continua/cancela a transação; NÃO avalia intent_shift
                     |
                     +-- NÃO -> libera EnterpriseRouter para avaliar intent_shift
```

### TransactionParameterExtractor

Novo componente:

`libs/agent_framework/src/agent_framework/runtime/transaction_parameters.py`

A extração textual dos parâmetros de negócio é feita exclusivamente por LLM. O componente recebe:

- nome da tool/transação ativa;
- parâmetros atualmente pendentes;
- argumentos já conhecidos;
- schema/tipos declarados em `tools.yaml` quando disponíveis;
- descrição da tool;
- mensagem atual do usuário.

Ele não conhece nomes de domínio como `order_id`, `reason`, `subject`, `valor`, TIM ou retail. Não há regex de entidades de negócio.

A LLM pode interpretar, por exemplo:

- `PED-1001` quando só há um parâmetro compatível pendente;
- `o pedido é PED-1001`;
- `PED-1001, desisti da compra` preenchendo dois parâmetros no mesmo turno;
- respostas com o nome do parâmetro seguido do valor;
- respostas apenas com o valor, quando semanticamente inequívocas.

Em caso de dúvida, o prompt manda retornar `null`. Uma nova solicitação não deve ser transformada em valor de parâmetro.

### Separação de responsabilidades

`tool_policies.yaml` continua sendo a fonte de verdade para `requires`.

`tools.yaml` pode fornecer tipos via `args_schema` e descrição da tool para melhorar a interpretação sem introduzir código específico de domínio.

`mcp_parameter_mapping.yaml` continua responsável pelos parâmetros auxiliares/contrato MCP. As strategies do mapper são explicitamente excluídas dos campos presentes em `policy.requires`, para não misturar extração MCP com coleta transacional.

O `EnterpriseRouter` usa o mesmo extrator LLM apenas como *probe* de precedência. Se pelo menos um parâmetro pendente for encontrado, o turno permanece no estado transacional. Os valores extraídos são colocados no metadata da decisão e reutilizados pelo runtime, evitando uma segunda chamada LLM no mesmo turno.

### Profile LLM

Foi adicionado aos templates:

```yaml
transaction_parameter_extraction:
  provider: oci_openai
  model: openai.gpt-4.1-mini
  temperature: 0
  max_tokens: 500
  timeout_seconds: 8
```

Generation/component:

- `llm.transaction_parameter_extraction`
- `transaction_parameter_extraction`

### Limpeza de estado

Em `intent_shift`, `transaction_pre_validation` da transação abandonada é removido para não contaminar a nova transação. O resultado de pre-validation continua preservado enquanto pertence à própria transação para auditoria.

### Testes adicionados

`tests/test_transaction_parameter_llm_precedence.py`

Cobertura:

1. dois parâmetros extraídos no mesmo turno;
2. um parâmetro preenchido ganha precedência sobre keyword que indicaria outra intent;
3. nenhum parâmetro encontrado libera `intent_shift`;
4. ausência do antigo `_extract_action_arguments()` hardcoded;
5. confirmação `sim` ganha precedência sobre intent shift.

### Correção de loop entre transação e intent

> Conteúdo consolidado a partir de `FIX_TRANSACTION_INTENT_LOOP.md`.

Correção aplicada em 2026-08-20 para impedir que uma sessão fique presa em `COLLECTING_PARAMETERS` ou `AWAITING_CONFIRMATION` quando o usuário muda explicitamente de assunto.

### Comportamento corrigido

Antes:

1. uma transação entrava em `COLLECTING_PARAMETERS`;
2. `next_state` forçava o mesmo agente via `state_policies`;
3. toda mensagem seguinte era tratada como tentativa de preencher o parâmetro faltante;
4. uma nova intenção como `quais sao meus servicos` permanecia presa no fluxo anterior.

Agora:

- o `EnterpriseRouter` verifica mudança explícita de intenção antes de aplicar o lock de estado;
- keyword explícita tem prioridade;
- quando necessário, o LLM router pode detectar mudança com confiança >= `router.confidence_threshold`;
- a decisão recebe `metadata.transaction_interruption=intent_shift`;
- o runtime encerra a transação pendente como `CANCELLED`, limpa `next_state`, parâmetros e latches, e prossegue com a nova intent;
- cancelamentos explícitos como `cancele essa operação anterior` funcionam também durante `COLLECTING_PARAMETERS`.

### Testes adicionados

- mudança de intent durante `COLLECTING_PARAMETERS`;
- resposta curta/baixa confiança permanece na transação;
- cancelamento explícito durante coleta de parâmetros;
- limpeza do estado transacional antes de executar a nova intent.

Testes focados: 19 passed.

### Evidência operacional de execução

> Conteúdo consolidado a partir de `docs/TRANSACTION_OPERATIONAL_EVIDENCE_FIX.md`.

### Problem

A confirmed transactional tool result was available only in the execution turn. On a later read-only turn, conversational memory could still mention the prior transaction (for example, a cancellation protocol), while the groundedness judge received only the current MCP results. This could classify a factually correct follow-up as unsupported.

### Fix

The framework now records completed/failed transactional tool outcomes as bounded operational evidence in LangGraph state/checkpoint (`transaction_evidence`). This is operational state, not Long Term Memory.

For each new turn, the runtime correlates previous transaction evidence with the current resource using generic identifiers (`*_id`, `order_id`, `invoice_id`, `asset_id`, `resource_key`, etc.). Only relevant evidence is materialized as `relevant_transaction_evidence`.

The same relevant evidence is:

- injected into the answering LLM prompt;
- merged with current MCP results for groundedness judges;
- exposed in response metadata as `transaction_evidence` for diagnostics;
- emitted with the completion telemetry event.

The history is bounded to the 10 most recent transaction outcomes, and at most 5 correlated entries are injected for a turn.

### Expected retail example

1. `cancelar_pedido(PED-1001)` returns protocol `CANCEL-2026-001`.
2. The result is persisted as transaction evidence.
3. The next `consultar_pedido(PED-1001)` returns `EM_TRANSPORTE`.
4. The answering agent and groundedness judge receive both the current order result and the prior cancellation evidence.
5. A response that mentions `CANCEL-2026-001` is grounded rather than treated as an unsupported claim.

### Validação integrada Backend/MCP

> Conteúdo consolidado a partir de `Documentacao/VALIDACAO_TRANSACIONAL_BACKEND_MCP.md`.

### Correções implementadas

- `mcp_tools` é tratado como allowlist, não como lista de execução automática.
- Tools `read_only` continuam disponíveis para enriquecimento de contexto.
- Somente uma tool transacional compatível com a solicitação é selecionada.
- `require_confirmation: true` cria `pending_tool_call` e `AWAITING_CONFIRMATION`.
- O turno de confirmação executa a chamada pendente com `confirmed: true`.
- O estado expõe `selected_tool_call`, `tool_policy_result`, `confirmation_required`, `confirmation_received` e `transaction_status`.
- `reason` foi padronizado entre catálogo, mapping e FastMCP Retail.
- Pedido `123` e `PED-ENTREGUE` retornam status `ENTREGUE` para testes positivos.
- A keyword genérica `produto` foi removida da intenção Telecom para não capturar devoluções Retail.
- Templates `Normal` e `Route_Stickness` em `Tuning-Performance` foram atualizados.

### Teste recomendado

1. `Quero devolver o pedido 123 porque me arrependi da compra.`
2. Esperado: `transaction_status=AWAITING_CONFIRMATION`, sem execução de `solicitar_devolucao`.
3. `Sim, confirmo a devolução.`
4. Esperado: `transaction_status=COMPLETED` e execução única de `solicitar_devolucao`.

### Resultado automatizado

```text
7 passed
```

### Arquivos de origem

Os arquivos abaixo foram consolidados neste manual:

- `docs/TRANSACTION_STATE_DEVELOPER_GUIDE.md`
- `docs/ADR_TRANSACTIONAL_WORKFLOW_ENGINE.md`
- `Documentacao/IMPLEMENTACAO_WORKFLOWS_TRANSACIONAIS.md`
- `FIX_TRANSACTION_PARAMETER_PRECEDENCE.md`
- `FIX_TRANSACTION_INTENT_LOOP.md`
- `docs/TRANSACTION_OPERATIONAL_EVIDENCE_FIX.md`
- `Documentacao/VALIDACAO_TRANSACIONAL_BACKEND_MCP.md`

### Regra de manutenção

Novas correções ou evoluções deste tema devem atualizar este documento consolidado. Release notes podem continuar existindo como histórico, mas não devem ser necessárias para compreender ou implementar a funcionalidade.


## Resolução canônica e revalidação de domínio antes da execução

Quando uma pré-validação resolve uma referência do usuário para uma entidade canônica, o framework **não deve simplesmente sobrescrever o parâmetro e executar a tool originalmente escolhida**. O contrato separa três valores:

```text
requested_subject = "youtube"
resolved_subject  = "Youtube Premium"
execution_subject = "Youtube Premium"
```

O validador de domínio pode devolver `transaction_decision` com:

```json
{
  "resolved_arguments": {"subject": "Youtube Premium"},
  "target_tool": "tratar_vas_estrategico",
  "action_changed": true,
  "requires_reconfirmation": true,
  "confirmation_message": "Identifiquei o serviço Youtube Premium. Esse serviço possui tratamento específico. Você deseja prosseguir?"
}
```

Responsabilidades:

- **Framework:** preserva argumentos solicitados, aplica apenas os argumentos canônicos declarados pelo validador, atualiza a transação para a `target_tool`, respeita `requires_reconfirmation` e mantém a decisão na evidência de pré-validação.
- **Agente/domínio:** decide classe, política e tool efetiva. O framework não conhece regras como “Youtube Premium é estratégico”.
- **MCP/backend:** executa a operação final já decidida pelo domínio.

Se a canonicalização não alterar a ação (`Tamboro` → `Tamboro Mensal`, por exemplo), a tool pode permanecer a mesma. Se a resolução alterar classe/política/tool, a decisão de domínio precisa ocorrer **antes da confirmação e da execução**. Em caso de ambiguidade ou baixa confiança, o validador deve pedir nova coleta/clarificação em vez de promover silenciosamente um candidato.

### Troubleshooting: resolved_subject correto, mas tool recebe o texto original

Sintoma: a pré-validação registra `resolved_subject="Youtube Premium"`, porém a execução ainda recebe `subject="youtube"`. Verifique se o validador retorna `transaction_decision.resolved_arguments` e se o runtime aplicou a decisão antes de congelar `pending_tool_call`/`confirmation_snapshot`.

Sintoma: a entidade foi resolvida corretamente, mas a tool final continua inadequada. Verifique `transaction_decision.target_tool`; a reclassificação de domínio pertence ao agente/validador, não ao framework.

Para domínios que possuem uma classificação autoritativa no detalhe do backend, a revalidação deve usar essa evidência antes de categorias agregadas. No Contas, por exemplo, `invoice_detail.parsed_content` preserva `classe=avulso|estrategico|bundle`; `billing_analysis` pode agrupar o mesmo item em seções mais amplas como `streaming` ou serviços de parceiros. A entidade canônica pode ser descoberta por qualquer evidência autorizada, mas a **decisão de negócio** deve priorizar a fonte que preserva a classificação de domínio. Se houver conflito de classificação, não troque a ação silenciosamente: mantenha a operação original ou peça esclarecimento conforme a política do agente.


## Confirmação transacional semântica: SIM / NAO / CONTINUAR

Transações em `AWAITING_CONFIRMATION` usam duas camadas, nesta ordem:

1. **Parser determinístico** para confirmações/recusas explícitas (`sim`, `não`, `confirmo`, `pode fazer`, etc.). Esse caminho continua sendo o mais barato, rápido e seguro e **não chama LLM**.
2. **Fallback semântico por LLM** somente quando o parser determinístico retorna inconclusivo. O fallback reutiliza o mesmo mecanismo declarativo de `expected_input.semantic_classifier` dos workflows pausados e injeta a pergunta pendente, o histórico recente relacionado ao mesmo tema e a fala atual.

A configuração fica em `config/routing.yaml`, sob `router.transaction_confirmation.semantic_fallback`:

```yaml
router:
  transaction_confirmation:
    semantic_fallback:
      enabled: true
      allowed_values: [SIM, NAO, CONTINUAR]
      confirm_values: [SIM]
      reject_values: [NAO]
      continue_values: [CONTINUAR]
      include_relevant_context: true
      profile_name: router
      prompt: |
        Classes permitidas: {{ allowed_values }}
        Pergunta pendente:
        {{ pending_prompt }}
        Histórico relevante:
        {{ relevant_conversation_context }}
        Resposta atual:
        {{ user_input }}
```

### Significado das classes

- `SIM`: aceite inequívoco da ação pendente. Exemplos: `isso mesmo, pode confirmar`, `é isso`, `pode seguir`, quando o contexto torna o aceite claro.
- `NAO`: recusa inequívoca da ação pendente. Exemplos: `melhor não`, `não quero mais`, `cancela isso`.
- `CONTINUAR`: a fala não confirma nem rejeita de forma inequívoca. Exemplos: pergunta adicional, correção de parâmetro, informação nova, ambiguidade ou possível mudança de assunto. Nesse caso a tool não é executada por confirmação.

### Exemplo

Contexto:

```text
Cliente: quero cancelar o Tamboro Mensal
Agente: Você confirma o cancelamento do serviço Tamboro Mensal?
Cliente: isso mesmo, pode confirmar
```

O parser determinístico não precisa conhecer literalmente `isso mesmo, pode confirmar`. O fallback recebe:

```text
pending_prompt = "Você confirma o cancelamento do serviço Tamboro Mensal?"
relevant_conversation_context = histórico recente do mesmo fluxo
user_input = "isso mesmo, pode confirmar"
```

e deve retornar apenas:

```text
SIM
```

O router então publica em `route_decision.metadata`:

```json
{
  "transaction_turn_consumed": true,
  "transaction_confirmation_decision": "confirm",
  "transaction_confirmation_source": "semantic"
}
```

O `AgentRuntime` reutiliza essa decisão e **não tenta reclassificar a mesma fala com o parser determinístico**. Isso evita a regressão em que o router entende semanticamente a confirmação, mas o runtime volta a tratá-la como inconclusiva.

### Precedência e compatibilidade

A funcionalidade é aditiva. Entradas determinísticas já suportadas continuam com o mesmo comportamento e sem custo adicional de LLM. O fallback semântico só roda quando a primeira camada não consegue decidir. Assim, `sim` e `não` continuam tendo precedência absoluta sobre `intent_shift`. Uma saída `CONTINUAR` não confirma nem rejeita automaticamente a transação; o fluxo normal pode então avaliar continuação contextual ou mudança de intenção conforme as políticas existentes.

### Observabilidade

Para confirmações semânticas, o framework registra a geração como `transaction.confirmation.semantic_classifier` e acrescenta ao metadata do roteamento a fonte `semantic`, a classificação retornada e o contexto conversacional relevante utilizado. Para confirmações literais, a fonte permanece `deterministic`.

### Compatibilidade de interrupts duráveis no pause/resume

O runtime não usa `snapshot.next` isoladamente para decidir se um workflow está pausado. Um `next` pode representar trabalho auxiliar do LangGraph, inclusive nós sintéticos criados pelo framework como `__pause` e `__continue`.

A pausa é reconhecida por um interrupt real. Dependendo da versão do LangGraph/checkpointer, esse interrupt pode aparecer em `task.interrupts` ou persistido em `snapshot.values["__interrupt__"]`. O runtime aceita ambas as formas e deduplica o payload quando as duas são expostas simultaneamente.

Isso evita dois falsos diagnósticos:

- considerar `snapshot.next` como `PAUSED` quando não existe interrupt real;
- considerar um `next=("<node>__pause",)` como erro de trabalho pendente quando o interrupt está persistido em `__interrupt__`.

Em workflows com `expected_input.semantic_classifier`, os tokens internos `SIM`, `NAO` e `CONTINUAR` continuam sendo valores de controle do resume e não devem ser confundidos com resposta final ao cliente.
