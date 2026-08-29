# 12 — Input Guardrail Feedback and Blocked-Turn Semantics

## Goal

This document describes how `AgentWorkflow`, implemented in `app/workflows/agent_graph.py`, should handle a turn interrupted by an input guardrail without turning every interruption into a generic “security rule” message.

The core rule is to keep three concerns separate:

1. **the guardrail technical decision**, used by the runtime and observability;
2. **the user-facing message**, appropriate to the type of block or clarification need;
3. **the turn state**, which must not carry routing, tool, or judge data from a turn that was interrupted before those stages.

## Expected flow

```text
user message
    ↓
input_guardrails
    ↓
allowed?
 ├─ yes → routing → tools/agent → composition → output_guardrails
 │
 └─ no
      ↓
    select public handling
      ↓
    clear routing/tools/judges state for this turn
      ↓
    build a safe user-facing message
      ↓
    output_guardrails
      ↓
    persistence/response
```

A blocking input guardrail must be decided **before any side-effecting tool is executed**.

## Internal `reason` is not the user response

The `reason` field should remain available to logs, traces, events, and diagnostics. It should not be exposed verbatim when it may reveal internal mechanisms or when the technical wording is not appropriate for the end user.

Example:

```text
COER.reason = "utterance is incomprehensible or contains an ambiguous negation"
```

A public response may be:

```text
"I could not fully understand your last message because it seems incomplete or ambiguous. Could you rephrase or complete what you meant?"
```

## Handling by guardrail type

Exact behavior remains configurable, but the expected semantics are:

| Guardrail | Recommended public handling |
|---|---|
| `COER` | ask for clarification/rephrasing; do not frame ordinary ambiguity as a security incident |
| `PINJ` | block safely without describing the internal mechanism |
| `DLEX_IN` | block or request reformulation without exposing internal/sensitive data |
| `INPUT_SIZE` | ask the user to reduce the input |
| `TOX` | apply the configured policy for inappropriate content |
| `CMP` | respond according to the compliance policy |
| unknown | use a safe generic fallback |

## Clearing blocked-turn state

When input is blocked before routing, the final state for that turn must not reuse residual data from the previous turn.

At a minimum, the workflow should avoid presenting these as current:

```text
route_decision
mcp_tools
mcp_results
judge_results
```

Metadata should clearly indicate that the turn was interrupted at the input-guardrail stage.

This prevents misleading diagnostics such as:

```text
route = blocked
mcp_results = [tool executed]
```

when the tool result actually belongs to the previous turn.

## The public message also goes through output guardrails

A response created because of an input block is still agent output. Therefore it should follow the same output-validation pipeline before reaching the user.

This allows `DLEX_OUT`, `PINJ`, `TOXOUT`, Output Supervisor, and other policies to remove or sanitize information that should not be exposed.

## COER, `expected_input`, and `reprompt` in paused workflows

When an active `expected_input.semantic_classifier` exists, the framework may delegate semantic interpretation to the workflow contract instead of immediately treating an ambiguous input as a generic `COER` block. In this mode, the guardrail may be recorded as allowed/delegated, for example with mechanism `expected_input_semantic_classifier`.

The workflow remains responsible for distinguishing:

```text
valid, meaningful reply       -> valid class / option_action
insufficient or meaningless   -> unmatched_value -> reprompt
```

Example:

```yaml
expected_input:
  allowed_values: [SIM, NAO, CONTINUAR]
  reprompt: "I did not understand. Did this explanation resolve your question? Please answer yes or no."
  semantic_classifier:
    enabled: true
    unmatched_value: OUTRO
    option_actions:
      CONTINUAR:
        action: contextual_reentry
```

Under this contract, `CONTINUAR` does not mean "anything other than SIM or NAO". It represents a **coherent, contextual** utterance that continues the topic. Input such as `ano`, which has insufficient meaning for the pending prompt, should return sentinel `OUTRO` and produce the `reprompt`, while keeping the same workflow paused.

`OUTRO` must not be added to `allowed_values` or sent to the runtime as a resume value. See [03 — Transactional Workflows and State](./03_transaction_workflows_and_state.md#expected_inputsemantic_classifierunmatched_value-and-reprompt) for the full contract.

## Relationship with `agent_graph.py`

This feature belongs to template orchestration because it defines precedence between graph nodes and blocked-turn state semantics.

When changing `app/workflows/agent_graph.py`, preserve these invariants:

- `input_guardrails` runs before routing/tools;
- an input block does not execute a transactional action after the block;
- the public response is not the raw guardrail `reason`;
- residual routing/tools/judges state does not survive as the blocked turn result;
- the public message passes through `output_guardrails` before persistence/response.

The same semantics must be preserved in the official templates and equivalent variants under `Tuning-Performance`.

## Troubleshooting

### The user receives “I could not continue because of a security rule” for a merely incomplete phrase

Check:

1. which guardrail returned `allowed=false`;
2. whether `COER` is handled as clarification rather than a generic security block;
3. whether the blocked branch builds a guardrail-specific public message;
4. whether the generic fallback is used only when no specific handling exists.

### Metadata shows a tool as executed while `route=blocked`

Check whether the blocked branch clears transient turn state before returning. Also confirm that the tool was not executed in the same turn before input-guardrail evaluation.

### The block response exposes internal details

Do not use `reason` directly as user-facing text. Generate the public message and keep `reason` for observability only.

### The block response skips output guardrails

Check the graph edge. The expected path is:

```text
input_guardrails blocked
→ build public response
→ output_guardrails
→ persist
```

not:

```text
input_guardrails blocked
→ persist
```

## Recommended regression tests

Cover at least:

- `COER=false` asks for clarification instead of returning a generic security message;
- with `expected_input.semantic_classifier.unmatched_value`, incoherent/insufficient input triggers `reprompt` and keeps the workflow `PAUSED`;
- meaningful input outside literal SIM/NAO can still follow `CONTINUAR -> contextual_reentry` without being confused with incoherent input;
- blocked branch does not retain previous-turn `mcp_results`/routing;
- no transactional tool executes after an input block;
- the public message passes through output guardrails;
- an unknown guardrail still has a safe generic fallback.
