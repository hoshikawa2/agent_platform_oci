
### Documentation Alignment Validation

### Purpose

Record how this version's documentation was reorganized and which sources developers should trust.

### Structural decision

The root `README_en.md` / `README.md` is the **single end-to-end main tutorial**.

The former `01_architecture_and_agent_development.md` was removed because it repeated much of the README but not all of it. That created ambiguity: two documents appeared to teach the same workflow while one was partial.

The new structure replaces it with `01_architecture_and_concepts.md`, containing only architecture, concepts, responsibilities and extension criteria.

### `README_old2.md` validation

`Documentacao/README_old2.md` remains useful as historical material but is not the primary development source.

Later evolution found in the current README/code includes SPECs/SDDs, richer `llm_profiles.yaml` guidance, Channel Gateway, canonical contracts, current memory composition, `RuntimeContext`, tool helpers, transaction helpers, direct MCP responses and gateway/RAG/memory/policy evolution.

### Main README correction

The generated package corrects this typo:

```python
from app.agents.financeiro_agent import FinanceirotAgent
```

to:

```python
from app.agents.financeiro_agent import FinanceiroAgent
```

The correct class is confirmed by code and the rest of the documentation.

### APIs confirmed in the current implementation

```python
AgentRuntimeMixin.get_runtime_context()
AgentRuntimeMixin.normalize_tools_by_intent()
AgentRuntimeMixin.build_tool_arguments()
AgentRuntimeMixin.execute_tools_for_intent()
AgentRuntimeMixin.prepare_memory_context()
AgentRuntimeMixin.build_messages()
AgentRuntimeMixin.transaction_state_patch()
AgentRuntimeMixin.transaction_clarification_message()
AgentRuntimeMixin.transaction_confirmation_message()
AgentRuntimeMixin.build_direct_mcp_answer()
```

### Trust order

1. version code;
2. main README for the same version;
3. SPECs/SDDs;
4. specialized manuals;
5. release notes;
6. `README_old*` documents.

### Future maintenance rule

A feature evolution should update:

1. the main README **only when the normal development path changes**;
2. the feature's specialized manual with technical detail, behavior, configuration and troubleshooting;
3. the SPEC when a contract changes;
4. a release note when historical recording is needed.

Do not create another “main manual” for a feature. Do not keep functional corrections permanently only in release notes.
