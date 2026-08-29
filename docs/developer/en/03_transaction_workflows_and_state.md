### Transactional Workflows and State

### How to use this manual

This is a **specialized reference manual**. It does not replace the main tutorial.

- To create an agent from start to finish, use [`README_en.md`](../../../README_en.md).
- Use this document when you need to implement, deepen, or diagnose **transaction state, parameter collection, confirmation, pause/resume, and operational evidence**.
- Historical examples consolidated here should be read in light of the framework's current API.
- In case of divergence, the code for the version and the current `README_en.md` take precedence.

### Relationship with the main tutorial

The `README_en.md` presents this capability in the normal development flow. This manual brings together details that were distributed across `docs/`, `Documentacao/`, release notes, validations, and specialized guides.

The goal here is to answer **“how does this feature work in depth and how do I solve problems with it?”**, without turning this file into a second copy of the main tutorial.

### Scope

Transaction state, parameter collection, confirmation, pause/resume, and operational evidence.

### Consolidated technical content

### Transactional Workflows, Multi-turn State, and Resume

Implementation guide for multi-step operations, canonical transaction-state source, confirmation, parameter merge, pause/resume, operational evidence, and routing interaction.

### How to use this document

This is the consolidated development document for this subject. It brings together architecture, configuration, examples, runtime behavior, compatibility, tests, and troubleshooting that were previously distributed across several files. Source sections were preserved when they provided distinct technical details; release notes were incorporated as current behavior or correction history.

### Multi-turn transaction-state guide

> Content consolidated from `docs/TRANSACTION_STATE_DEVELOPER_GUIDE.md`.

This document defines the operational contract for multi-turn transactions in Agent Framework OCI. It is normative for hosts and templates that use `AgentRuntime`, LangGraph checkpointing, and transactional tools.

### 1. Goal

A transaction can span several turns. Example:

```text
Usuário: quero cancelar o pedido
Framework: informe o número do pedido
Usuário: PED-1001
Framework: confirma o cancelamento?
Usuário: sim
Framework: executa a tool
```

The framework must preserve the transaction across all these turns without depending on LLM reclassification, keyword routing, or re-extraction of parameters that have already been obtained.

### 2. Canonical transaction-state source

The canonical state for the in-progress transaction is `active_transaction`.

```python
active_transaction: dict[str, Any]
last_transaction: dict[str, Any]
```

Every `AgentState` used by a host that enables multi-turn transactions **MUST** declare both fields. Because LangGraph uses the state schema for persistence/checkpointing, a field created only dynamically by the runtime is not a safe durable contract.

Minimum example:

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

### 3. Role of each field

| Field | Role | Rule |
|---|---|---|
| `active_transaction` | Canonical source of the active transaction | Must survive checkpoint/resume while the transaction is active. |
| `last_transaction` | Snapshot of the last terminal transaction | Used for audit, evidence, and controlled continuity; it does not automatically reactivate the transaction. |
| `transaction_status` | Current logical state | E.g. `COLLECTING_PARAMETERS`, `AWAITING_CONFIRMATION`, `COMPLETED`, `CANCELLED`, `OUT_OF_SCOPE`. |
| `missing_parameters` | Parameters still required | Must reflect canonical transaction state, not only the current message. |
| `selected_tool_call` | Auxiliary/compatibility state | Must not replace `active_transaction` as the canonical source. |
| `pending_tool_call` | Auxiliary/compatibility state | May be used for compatibility, but not as the primary latch. |
| `next_state` | Workflow routing guidance | Helps keep the correct node/agent during collection/confirmation. |
| `transaction_pre_validation` | Pre-validation evidence | Preserves validation results before confirmation/execution. |
| `transaction_evidence` | Execution evidence | Preserves transaction results and execution trail. |

### 4. Recommended lifecycle

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

Alternative terminal outcomes:

```text
CANCELLED
OUT_OF_SCOPE
FAILED
```

The runtime may represent some phases internally without a separate public `transaction_status`. The requirement is to preserve the latch and not lose arguments already collected.

### 5. Incremental parameter merge

A later response must complement the existing transaction, never recreate it only from the current text.

```python
existing = dict((state.get("active_transaction") or {}).get("arguments") or {})
new_values = {"valor": "71.99"}
arguments = {**existing, **new_values}
```

Expected example:

```text
Turno 1: subject = "TIM CTRL Redes Sociais 8.0"
Turno 2: valor = "71.99"
Resultado: subject + valor permanecem disponíveis
```

### 6. Routing precedence during a transaction

When an `active_transaction` exists in `COLLECTING_PARAMETERS`, the message must first be evaluated as a possible answer to the pending parameters.

Normative precedence:

1. pending parameter clearly filled → continue the transaction;
2. explicit cancellation/abandonment → cancel the transaction;
3. unequivocal new intent → interrupt the transaction and route;
4. generic keyword from the same domain/agent → **do not** interrupt the transaction;
5. ambiguous message → keep the transaction and clarify.

Examples:

| Current state | Message | Correct result |
|---|---|---|
| `retail_order_cancel`, missing `order_id` | `PED-1001` | Continue cancellation and fill `order_id`. |
| `retail_order_cancel`, missing `order_id` | `o pedido é o PED-1001` | Continue cancellation; `pedido` must not become tracking. |
| dispute, missing `valor` | `R$ 71,99` | Continue dispute and fill `valor`. |
| cancellation pending | `esquece, quero ver minha fatura` | Explicit interruption allowed. |
| cancellation pending | `quero rastrear pedido` | Unequivocal shift to tracking allowed. |

### 7. Checkpoint and resume

Before running normal routing, the host must restore the checkpoint using the same conversation identity (`tenant_id`, `agent_id`, `session_id`/`conversation_key` according to the host contract).

After restoration:

```text
active_transaction existe
       ↓
status ativo?
       ↓ sim
retomar a transação antes de keyword routing / continuity LLM
```

A `COLLECTING_PARAMETERS` state without `active_transaction` must be treated as a state inconsistency and observed/diagnosed; it must not silently restart the tool from the current message.

### 8. What belongs to the framework and what belongs to the agent

Framework:

- latch persistence;
- argument merge;
- collection/confirmation states;
- resume precedence;
- deterministic confirmation;
- idempotency and evidence;
- checkpoint/resume.

Agent:

- domain-tool definitions;
- required parameters and domain messages;
- domain-specific eligibility rules;
- domain-specific pre-validation, when applicable;
- final customer response.

The agent must not implement a second transactional engine in parallel with `AgentRuntime`.

### 9. Checklist for new hosts/templates

- [ ] `AgentState` declares `active_transaction`.
- [ ] `AgentState` declares `last_transaction`.
- [ ] `transaction_status` and `missing_parameters` are part of state when used.
- [ ] The host uses checkpointing compatible with the state schema.
- [ ] The same `conversation_key` is used across turns of the same conversation.
- [ ] Previously collected parameters are merged with new values.
- [ ] Parameter answers take precedence over generic keyword routing.
- [ ] Explicit intent changes remain possible.
- [ ] The agent uses `transaction_state_patch(state)` when returning transactional responses if the template requires it.
- [ ] Multi-turn tests exist for collection, confirmation, interruption, and resume.

### 10. Minimum regression tests

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

- rebuilding the transaction only from the last message;
- using `selected_tool_call` as the only latch source;
- removing `active_transaction` from `AgentState` because it appears redundant;
- allowing a generic keyword such as `pedido` to interrupt `order_id` collection;
- storing parameters only in local node variables;
- duplicating transactional confirmation in the agent prompt;
- clearing the latch before terminal state.

### 12. Project references

- `specs/SPEC-002-Agent-Runtime.md`
- `specs/SPEC-010-Agent-Development.md`
- `templates/agent_template_backend/app/state.py`
- `libs/agent_framework/src/agent_framework/runtime/agent_runtime.py`
- `libs/agent_framework/src/agent_framework/routing/enterprise_router.py`
- `Tuning-Performance/Deterministic_Transactional_Workflow/`
- `Tuning-Performance/Transaction_Pre_Validation/`
- `Tuning-Performance/Transaction_Evidence/`

### Transactional workflow engine architectural decision

> Content consolidated from `docs/ADR_TRANSACTIONAL_WORKFLOW_ENGINE.md`.

### Decision

Add an optional deterministic execution capability based on LangGraph to the framework. The engine is generic; YAML definitions and domain actions remain in the agents.

### Rationale

Multi-step operations with side effects must not depend on the LLM to select the critical sequence. The solution reduces tokens, latency, and variability, while improving auditability, testing, and versioning.

### Compatibility

`execution.mode` defaults to `direct_tool`. Existing projects continue to use MCP directly. Workflow adoption is explicit per tool and may be controlled through `ENABLE_TRANSACTIONAL_WORKFLOWS`.

### Scope limits of this delivery

The foundation includes validation, file-based versioning, registry, sync/async execution, conditions, per-node retry, graph cache, and a policy adapter. Enterprise execution-record persistence, compensation/Saga, scope authorization, and workflow-specific IC/NOC emission must be connected to the abstractions available in each deployment before use in critical financial transactions.

### Deterministic workflow implementation

> Content consolidated from `Documentacao/IMPLEMENTACAO_WORKFLOWS_TRANSACIONAIS.md`.

### Delivery

An optional capability was added to `agent_framework_oci` to execute multi-step transactions as deterministic workflows compiled into LangGraph.

### New module

`libs/agent_framework/src/agent_framework/workflows/`

- `models.py`: Pydantic contracts and structural validation;
- `repository.py`: active-version resolution and immutable YAML reading;
- `registry.py`: decoupled registration of sync/async actions;
- `runtime.py`: StateGraph compilation, cache, and execution;
- `tool_executor.py`: integration with tool policy;
- `__init__.py`: public API.

### Expanded policy

`ToolPolicy` now accepts:

```yaml
execution:
  mode: direct_tool | workflow | agent
  workflow: nome_do_workflow
  version: active | 1
```

The default remains `direct_tool`, preserving compatibility.

### Configuration

The following were added:

- `ENABLE_TRANSACTIONAL_WORKFLOWS=false`;
- `WORKFLOWS_PATH=./workflows`.

### Template

Includes a complete order-return example with:

- confirmation and required fields from policy;
- versioned workflow YAML;
- domain actions in the backend;
- deterministic branching based on validation result.

### Validation performed

- `tests/unit/test_tool_policies.py`: 4 tests passed;
- Python compilation for framework, template, and new tests: passed;
- the new LangGraph functional test was created but could not be run in this container because `langgraph` is not installed in the environment. The dependency is already declared in the framework `pyproject.toml`.

### Scope and safety

This delivery creates the engine and policy integration. For critical production operations, it is still necessary to connect:

- persistent execution store;
- business idempotency in actions/APIs;
- scope authorization;
- workflow-specific IC/NOC telemetry;
- compensation/Saga where applicable;
- enterprise timeout and retry strategy.

These items are explicitly documented to avoid the false impression that retry by itself guarantees transactional safety.

### Parameter-collection precedence

> Content consolidated from `FIX_TRANSACTION_PARAMETER_PRECEDENCE.md`.

This correction removes hardcoded textual extraction of transactional parameters and collects `policy.requires` through a generic LLM extractor.

### Precedence rule

While an active transaction exists, the framework handles the turn in this order:

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

New component:

`libs/agent_framework/src/agent_framework/runtime/transaction_parameters.py`

Textual extraction of business parameters is performed exclusively by the LLM. The component receives:

- name of the active tool/transaction;
- currently pending parameters;
- already known arguments;
- schema/types declared in `tools.yaml` when available;
- tool description;
- current user message.

It does not know domain names such as `order_id`, `reason`, `subject`, `valor`, TIM, or retail. There is no regex for business entities.

The LLM can interpret, for example:

- `PED-1001` when only one compatible parameter is pending;
- `o pedido é PED-1001`;
- `PED-1001, desisti da compra`, filling two parameters in the same turn;
- answers with the parameter name followed by the value;
- answers containing only the value, when semantically unequivocal.

When in doubt, the prompt instructs the model to return `null`. A new request must not be transformed into a parameter value.

### Separation of responsibilities

`tool_policies.yaml` remains the source of truth for `requires`.

`tools.yaml` may provide types through `args_schema` and the tool description to improve interpretation without introducing domain-specific code.

`mcp_parameter_mapping.yaml` remains responsible for auxiliary parameters/MCP contract. Mapper strategies are explicitly excluded for fields present in `policy.requires`, so MCP extraction is not mixed with transactional collection.

The `EnterpriseRouter` uses the same LLM extractor only as a precedence *probe*. If at least one pending parameter is found, the turn remains in the transactional state. Extracted values are placed in decision metadata and reused by the runtime, avoiding a second LLM call in the same turn.

### LLM profile

The following was added to the templates:

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

### State cleanup

On `intent_shift`, the abandoned transaction's `transaction_pre_validation` is removed so it does not contaminate the new transaction. The pre-validation result remains preserved while it belongs to its own transaction for audit purposes.

### Tests added

`tests/test_transaction_parameter_llm_precedence.py`

Coverage:

1. two parameters extracted in the same turn;
2. one filled parameter takes precedence over a keyword that would indicate another intent;
3. no parameter found releases `intent_shift`;
4. absence of the old hardcoded `_extract_action_arguments()`;
5. `sim` confirmation takes precedence over intent shift.

### Transaction/intent loop fix

> Content consolidated from `FIX_TRANSACTION_INTENT_LOOP.md`.

Correction applied on 2026-08-20 to prevent a session from getting stuck in `COLLECTING_PARAMETERS` or `AWAITING_CONFIRMATION` when the user explicitly changes subject.

### Corrected behavior

Before:

1. a transaction entered `COLLECTING_PARAMETERS`;
2. `next_state` forced the same agent through `state_policies`;
3. every following message was treated as an attempt to fill the missing parameter;
4. a new intent such as `quais sao meus servicos` remained trapped in the previous flow.

Now:

- the `EnterpriseRouter` checks for an explicit intent change before applying the state lock;
- explicit keyword has priority;
- when necessary, the LLM router can detect a change with confidence >= `router.confidence_threshold`;
- the decision receives `metadata.transaction_interruption=intent_shift`;
- the runtime closes the pending transaction as `CANCELLED`, clears `next_state`, parameters, and latches, and proceeds with the new intent;
- explicit cancellations such as `cancele essa operação anterior` also work during `COLLECTING_PARAMETERS`.

### Tests added

- intent change during `COLLECTING_PARAMETERS`;
- short/low-confidence answer remains in the transaction;
- explicit cancellation during parameter collection;
- cleanup of transactional state before executing the new intent.

Focused tests: 19 passed.

### Operational execution evidence

> Content consolidated from `docs/TRANSACTION_OPERATIONAL_EVIDENCE_FIX.md`.

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

### Integrated Backend/MCP validation

> Content consolidated from `Documentacao/VALIDACAO_TRANSACIONAL_BACKEND_MCP.md`.

### Implemented corrections

- `mcp_tools` is treated as an allowlist, not as an automatic execution list.
- `read_only` tools remain available for context enrichment.
- Only one transactional tool compatible with the request is selected.
- `require_confirmation: true` creates `pending_tool_call` and `AWAITING_CONFIRMATION`.
- The confirmation turn executes the pending call with `confirmed: true`.
- State exposes `selected_tool_call`, `tool_policy_result`, `confirmation_required`, `confirmation_received`, and `transaction_status`.
- `reason` was standardized across catalog, mapping, and Retail FastMCP.
- Orders `123` and `PED-ENTREGUE` return status `ENTREGUE` for positive tests.
- The generic keyword `produto` was removed from the Telecom intent so it does not capture Retail returns.
- `Normal` and `Route_Stickness` templates in `Tuning-Performance` were updated.

### Recommended test

1. `Quero devolver o pedido 123 porque me arrependi da compra.`
2. Expected: `transaction_status=AWAITING_CONFIRMATION`, without executing `solicitar_devolucao`.
3. `Sim, confirmo a devolução.`
4. Expected: `transaction_status=COMPLETED` and a single execution of `solicitar_devolucao`.

### Automated result

```text
7 passed
```

### Source files

The files below were consolidated into this manual:

- `docs/TRANSACTION_STATE_DEVELOPER_GUIDE.md`
- `docs/ADR_TRANSACTIONAL_WORKFLOW_ENGINE.md`
- `Documentacao/IMPLEMENTACAO_WORKFLOWS_TRANSACIONAIS.md`
- `FIX_TRANSACTION_PARAMETER_PRECEDENCE.md`
- `FIX_TRANSACTION_INTENT_LOOP.md`
- `docs/TRANSACTION_OPERATIONAL_EVIDENCE_FIX.md`
- `Documentacao/VALIDACAO_TRANSACIONAL_BACKEND_MCP.md`

### Maintenance rule

New fixes or evolutions for this subject should update this consolidated document. Release notes may continue to exist as history, but they should not be required to understand or implement the feature.


## Canonical resolution and domain revalidation before execution

When pre-validation resolves a user reference to a canonical entity, the framework **must not blindly overwrite the parameter and execute the originally selected tool**. The contract keeps requested, resolved and execution values distinct.

A domain validator may return `transaction_decision` with `resolved_arguments`, `target_tool`, `action_changed`, `requires_reconfirmation`, and an optional customer-facing `confirmation_message`.

Responsibilities:

- **Framework:** preserve the requested arguments, apply only canonical arguments declared by the validator, update the transaction to the effective `target_tool`, honor reconfirmation, and retain the decision in pre-validation evidence.
- **Agent/domain:** decide business class, policy and effective tool. The framework must not know rules such as “Youtube Premium is strategic”.
- **MCP/backend:** execute the final operation chosen by the domain.

If canonicalization does not change the action, the current tool may remain valid. If entity resolution changes business class/policy/tool, domain revalidation must happen **before confirmation and execution**. Ambiguous or low-confidence resolution must request clarification instead of silently promoting a candidate.

### Troubleshooting: resolved_subject is correct but execution receives the original text

If pre-validation records `resolved_subject="Youtube Premium"` while execution still receives `subject="youtube"`, verify that the validator returns `transaction_decision.resolved_arguments` and that the runtime applies the decision before freezing `pending_tool_call` / `confirmation_snapshot`. If the canonical entity is correct but the final tool is wrong, inspect `transaction_decision.target_tool`; that business reclassification belongs to the domain validator, not to the framework.

For domains that expose an authoritative business classification in backend detail, revalidation should use that evidence before aggregated categories. In Contas, for example, `invoice_detail.parsed_content` preserves `classe=avulso|estrategico|bundle`, while `billing_analysis` may group the same item into broader sections such as `streaming` or partner services. Canonical entity discovery may use any authorized evidence, but the **business decision** should prioritize the source that preserves the domain classification. If classification evidence conflicts, do not silently change the action; preserve the current operation or request clarification according to the agent policy.


## Semantic transactional confirmation: SIM / NAO / CONTINUAR

Transactions in `AWAITING_CONFIRMATION` use two layers, in this order:

1. **Deterministic parser** for explicit confirmations/rejections (`sim`, `não`, `confirmo`, `pode fazer`, etc.). This remains the cheapest and safest path and **does not call an LLM**.
2. **LLM semantic fallback** only when the deterministic parser is inconclusive. The fallback reuses the same declarative semantic-classifier engine used by paused workflow `expected_input`, injecting the pending prompt, recent context related to the same topic, and the current user utterance.

Configuration lives in `config/routing.yaml` under `router.transaction_confirmation.semantic_fallback`:

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
        Allowed classes: {{ allowed_values }}
        Pending prompt:
        {{ pending_prompt }}
        Relevant context:
        {{ relevant_conversation_context }}
        Current user input:
        {{ user_input }}
```

`SIM` means an unambiguous acceptance, `NAO` an unambiguous rejection, and `CONTINUAR` means the utterance does not safely confirm or reject the pending action. Example: after `Você confirma o cancelamento do serviço Tamboro Mensal?`, the reply `isso mesmo, pode confirmar` can be classified as `SIM` without hardcoding that exact sentence.

When semantic confirmation succeeds, the router records:

```json
{
  "transaction_turn_consumed": true,
  "transaction_confirmation_decision": "confirm",
  "transaction_confirmation_source": "semantic"
}
```

`AgentRuntime` reuses this routed decision instead of re-running the deterministic parser. The change is additive: existing explicit yes/no inputs continue through the deterministic path with no extra LLM call. Semantic generations are named `transaction.confirmation.semantic_classifier` for observability.

### Durable interrupt compatibility in pause/resume

The runtime does not use `snapshot.next` alone to decide whether a workflow is paused. A truthy `next` may represent LangGraph helper work, including framework-generated synthetic nodes such as `__pause` and `__continue`.

A pause is recognized only from a real interrupt. Depending on the LangGraph/checkpointer version, that interrupt may be exposed through `task.interrupts` or persisted in `snapshot.values["__interrupt__"]`. The runtime supports both shapes and deduplicates the payload when both are present.

This prevents two false diagnoses:

- treating `snapshot.next` as `PAUSED` when no real interrupt exists;
- treating `next=("<node>__pause",)` as invalid pending work when the real interrupt is persisted under `__interrupt__`.

For workflows using `expected_input.semantic_classifier`, internal tokens such as `SIM`, `NAO`, and `CONTINUAR` remain resume control values and must not be confused with customer-facing output.
