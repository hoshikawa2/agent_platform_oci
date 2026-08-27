### Documentation Alignment Validation

### Goal

Record how the documentation for this version was reorganized and which sources developers should use.

### Structural decision

The root `README_en.md` is the **single end-to-end main tutorial**.

The former `01_architecture_and_agent_development.md` was removed because it repeated a large part of the README, but not all of it. This created ambiguity: two documents appeared to teach the same thing, but one was partial.

The new structure replaces that file with `01_architecture_and_concepts.md`, which contains only architecture, concepts, responsibilities, and extension criteria.

### Validation of `README_old2.md`

`Documentacao/README_old2.md` remains useful as history, but it is not the primary source for development.

Later evolutions were found in the current README and code, including:

- SPECs/SDDs;
- more complete `llm_profiles.yaml` configuration;
- Channel Gateway and canonical contracts;
- `memory` and `summary_memory` in the current agent lifecycle;
- `prepare_memory_context()` and `build_messages()`;
- `RuntimeContext`;
- `normalize_tools_by_intent()`;
- `build_tool_arguments()`;
- `execute_tools_for_intent()`;
- transaction-state helpers;
- direct MCP responses;
- evolution of gateways, RAG, memory, and policies.

### Correction applied to the main README

The following typo was corrected in the generated package:

```python
from app.agents.financeiro_agent import FinanceirotAgent
```

to:

```python
from app.agents.financeiro_agent import FinanceiroAgent
```

The correct class is confirmed by the code and the rest of the documentation.

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

1. code for the version;
2. main README for the same version;
3. SPECs/SDDs;
4. specialized manuals;
5. release notes;
6. `README_old*` documents.

### Future maintenance rule

A feature evolution should update:

1. the main README, **only if it changes the normal development path**;
2. the feature's specialized manual, with technical details, behavior, configuration, and troubleshooting;
3. the SPEC, when there is a contract change;
4. the release note, when it is necessary to record the historical change.

Do not create a new “main manual” for a feature. Do not keep functional fixes permanently only in release notes.
