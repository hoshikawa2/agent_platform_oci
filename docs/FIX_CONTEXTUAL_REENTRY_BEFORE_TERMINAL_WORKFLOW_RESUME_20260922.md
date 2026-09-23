# Fix: contextual reentry before terminal workflow resume

## Problem

A paused workflow with a declarative `expected_input.semantic_classifier` could receive a
compound reply such as:

```text
ainda nao. Eu nao contratei esse neymar jr
```

If the classifier returned only `NAO`, the framework immediately resumed the paused workflow.
A backend workflow was then free to enter a terminal branch (for example human handoff) before
the substantive remainder of the same user turn was reinterpreted by normal routing.

This is an orchestration problem in the framework, not a domain rule for billing and not a
frontend problem.

## Corrected precedence

Literal `expected_input` matches keep absolute precedence and are unchanged. For non-literal
semantic matches, when the workflow itself declares an option with
`option_actions.<option>.action: contextual_reentry`, the framework now performs one generic
precedence validation before committing to a normal workflow resume.

The validation asks only whether the current utterance is completely consumed by the selected
resume option or whether it also contains substantive information that still needs interpretation.
It contains no domain vocabulary and no hardcoded `SIM`/`NAO` business meaning.

The effective order is now:

1. deterministic `expected_input` exact match;
2. explicit global human-handoff control;
3. workflow `semantic_classifier`;
4. if the semantic result would resume and the contract declares `contextual_reentry`, validate
   whether substantive remainder exists;
5. substantive remainder -> `contextual_reentry` and normal routing;
6. pure reply -> resume paused workflow normally;
7. only after a genuine resume can the backend workflow reach its own terminal/handoff branch.

A workflow can explicitly disable this safeguard with:

```yaml
semantic_classifier:
  contextual_reentry_precedence: false
```

The default is enabled whenever a `contextual_reentry` option is declared.

## Observability

When reentry preempts a semantic resume, route metadata now includes:

- `contextual_reentry_preempted_resume: true`
- `initial_classifier_output`
- `contextual_reentry_precedence_raw_output`
- the existing contextual-reentry metadata (`original_input`, `classifier_output`, bounded context)

## Regression tests

Tests cover both directions:

- a compound negative reply whose first classifier result is `NAO` is protected from premature
  resume and is rerouted through contextual reentry;
- a pure semantic negative reply remains a normal workflow resume.
