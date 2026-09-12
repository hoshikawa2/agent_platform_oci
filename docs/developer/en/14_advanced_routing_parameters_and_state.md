### Advanced routing, parameters, and state

### Decision precedence

Routing is not a keyword list. Safe precedence is: explicit block/finalization; pending collection or transaction through `state_policies`; deterministic confirmation; deterministic intent; optional LLM fallback; and finally fallback/handoff. Pending state must win so short replies and isolated parameters do not jump to another agent.

The complete executable YAML is in the matching [Portuguese chapter](../pt/14_routing_parametros_e_estado_avancados.md). In `routing.yaml`, lower `priority` values win ties in the current template. `mcp_tools` limits candidates but does not authorize sensitive effects. `confidence_threshold` gates semantic results, `allow_handoff` permits an explicit agent change, and `domain` supplies scope metadata rather than replacing `agent`.

### Semantic confirmation

Constrain semantic confirmation with `allowed_values`, plus explicit confirm, reject, and continue sets. The prompt must include the allowed values and prohibit execution or invented facts. `include_relevant_context` contributes bounded context related to the pause. If model output does not match an allowed option, keep the transaction pending. Explicit yes/no remains deterministic; the LLM handles inconclusive language only.

### Identity, mapping, and extraction

`identity.yaml` resolves canonical customer, contract, interaction, account, resource, and session keys from the payload, prior `business_context`, or previous context. Validate required identity before MCP execution. A session identifier is not customer identity.

Recommended argument precedence is: already confirmed transaction value, explicit current value, canonical identity mapping, deterministic extraction, LLM/hybrid extraction, and default. A new explicit value may correct an old one; an inferred value must never overwrite a confirmed value.

For `strategy: hybrid`, test both regex and LLM paths. `pattern` and `group` require positive and negative tests. `description` is an operational extraction instruction, not decorative documentation. Type conversion must fail safely when ambiguous.

### Temporal reconciliation

Temporal reconciliation is a fallback only after ordinary collection leaves missing fields. Search relevant messages newest-first and bind values only to fields described by the tool schema/mapping. It must not cross tenant/agent/session, revive a closed transaction, recover a user-invalidated value, replace safe exact matching with dangerous fuzzy matching, or overwrite a confirmed field. Record value origin and correlation without retaining unnecessary sensitive text.

### Dynamic states and multi-agent behavior

Declare new collection and confirmation state fields only when they carry extra data; otherwise reuse generic transaction keys. Every new state needs a matching `state_policies` entry, cleanup on success/cancellation/intent shift, and routing tests. A new state without policy commonly loses route stickiness.

Router mode selects one agent. Supervisor mode coordinates multiple agents and changes cost, latency, state, and telemetry. Do not enable it merely to improve classification. Give subagents minimum context and authorized tools, scoped by `tenant_id:agent_id:session_id`; never share raw memory across agents.

Test keyword overlap, priority ties, below-threshold output, fallback, pending states, short confirmations, ambiguity, parameter correction, regex/LLM extraction, temporal history, and isolation. Run `pytest -q tests/test_advanced_developer_documentation.py`.
