from __future__ import annotations

import json
import pytest

from agent_framework.runtime.transaction_parameters import extract_transaction_parameters, reconcile_transaction_parameters


class _ContextAwareLLM:
    def __init__(self):
        self.prompt = ""

    async def ainvoke(self, messages, **kwargs):
        self.prompt = messages[-1]["content"]
        # This simulates a semantic extractor resolving the current reference
        # against the bounded conversation context. The values remain candidates;
        # authoritative validation belongs to the domain pre-validation step.
        return json.dumps({"subject": "Tamboro Mensal", "valor": 14.99}, ensure_ascii=False)


@pytest.mark.asyncio
async def test_contextual_reentry_separates_current_claim_from_prior_context_for_candidate_extraction():
    llm = _ContextAwareLLM()
    out = await extract_transaction_parameters(
        llm,
        text="é a de quatorze e noventa e nove",
        conversational_context=(
            "user: tem uma cobrança aqui que eu não reconheço\n"
            "assistant: Cobrança Tamboro Mensal no valor de R$ 14,99; "
            "TIM Fashion Mensal no valor de R$ 10,00."
        ),
        tool_name="contestar_cobranca",
        missing_parameters=["subject", "valor"],
        parameter_schema={
            "subject": {"type": "string", "description": "item concreto da fatura"},
            "valor": {"type": "number", "description": "valor explicitamente associado pelo cliente"},
        },
        tool_description="Contesta uma cobrança após validação autoritativa e confirmação.",
    )
    assert out == {"subject": "Tamboro Mensal", "valor": 14.99}
    assert "conversational_context:" in llm.prompt
    assert "Cobrança Tamboro Mensal" in llm.prompt
    assert "user_message: é a de quatorze e noventa e nove" in llm.prompt
    assert "Não trate texto do contexto como uma nova afirmação do cliente" in llm.prompt

class _TwoPassContextLLM:
    def __init__(self):
        self.calls = []

    async def ainvoke(self, messages, **kwargs):
        prompt = messages[-1]["content"]
        self.calls.append(prompt)
        # First pass: current utterance provides only the amount.
        if "user_message: é a de vinte e cinco e cinquenta" in prompt:
            return json.dumps({"subject": None, "valor": 25.50}, ensure_ascii=False)
        # Second bounded pass: previous USER utterance provides the missing entity.
        if "user_message: não reconheço esse Tamboro Mensal na minha fatura" in prompt:
            return json.dumps({"subject": "Tamboro Mensal"}, ensure_ascii=False)
        return "{}"


@pytest.mark.asyncio
async def test_contextual_reentry_second_pass_recovers_only_missing_candidate_from_prior_user_turn():
    from agent_framework.runtime.agent_runtime import AgentRuntimeMixin

    class Runtime(AgentRuntimeMixin):
        pass

    runtime = Runtime()
    runtime.llm = _TwoPassContextLLM()
    state = {
        "route_decision": {
            "metadata": {
                "contextual_reentry": True,
                "original_input": "é a de vinte e cinco e cinquenta",
                "relevant_conversation_context": (
                    "user: não reconheço esse Tamboro Mensal na minha fatura\n"
                    "assistant: identifiquei duas cobranças de Tamboro Mensal"
                ),
            }
        },
        "sanitized_input": "é a de vinte e cinco e cinquenta",
    }
    out = await runtime._extract_transaction_parameters(
        state=state,
        tool_name="contestar_cobranca",
        missing_parameters=["subject", "valor"],
        known_arguments={},
    )
    assert float(out["valor"]) == 25.5
    assert out["subject"] == "Tamboro Mensal"
    assert len(runtime.llm.calls) >= 2

class _CoherentTemporalLLM:
    """Simulates the structured decisions expected from temporal reconciliation."""
    def __init__(self):
        self.prompts = []

    async def ainvoke(self, messages, **kwargs):
        prompt = messages[-1]["content"]
        self.prompts.append(prompt)
        low = prompt.lower()
        # Product A + value X established.
        if "user_message: na verdade é tim fashion mensal" in low:
            return json.dumps({"fields": {
                "subject": {"decision": "resolved", "value": "TIM Fashion Mensal", "source": "current"},
                # Previous 14.99 was tied to the former product and must not be transplanted.
                "valor": {"decision": "clear", "value": None, "source": "history:1"},
            }}, ensure_ascii=False)
        if "user_message: na verdade é produto inexistente" in low:
            return json.dumps({"fields": {
                # Keep the newest candidate so authoritative validation can reject it.
                "subject": {"decision": "resolved", "value": "Produto Inexistente", "source": "current"},
                "valor": {"decision": "clear", "value": None, "source": "history:1"},
            }}, ensure_ascii=False)
        if "user_message: desculpa, era tamboro mensal mesmo" in low:
            return json.dumps({"fields": {
                "subject": {"decision": "resolved", "value": "Tamboro Mensal", "source": "current"},
                # Full temporal text makes the old amount coherent again with the restored product.
                "valor": {"decision": "resolved", "value": 14.99, "source": "history:2"},
            }}, ensure_ascii=False)
        return json.dumps({"fields": {
            "subject": {"decision": "preserve", "value": None, "source": "state"},
            "valor": {"decision": "preserve", "value": None, "source": "state"},
        }}, ensure_ascii=False)


@pytest.mark.asyncio
async def test_temporal_reconciliation_product_change_rechecks_old_value_as_part_of_coherent_set():
    from agent_framework.runtime.transaction_parameters import reconcile_transaction_parameters

    llm = _CoherentTemporalLLM()
    out = await reconcile_transaction_parameters(
        llm,
        text="na verdade é TIM Fashion Mensal",
        conversational_context=(
            "history:1: user: é R$ 14,99\n"
            "history:2: user: quero contestar Tamboro Mensal"
        ),
        tool_name="contestar_cobranca",
        parameter_names=["subject", "valor"],
        known_arguments={"subject": "Tamboro Mensal", "valor": 14.99},
        parameter_schema={
            "subject": {"type": "string", "description": "Nome do serviço, produto, item ou cobrança objeto da contestação."},
            "valor": {"type": "number", "description": "Valor monetário associado ao item objeto da contestação."},
        },
        tool_description="Contesta uma cobrança após validação.",
    )
    assert out["values"] == {"subject": "TIM Fashion Mensal"}
    assert out["clear_fields"] == ["valor"]
    assert out["provenance"]["subject"] == "current"


@pytest.mark.asyncio
async def test_temporal_reconciliation_invalid_new_product_does_not_erase_history_or_fall_back_silently():
    from agent_framework.runtime.transaction_parameters import reconcile_transaction_parameters

    llm = _CoherentTemporalLLM()
    history = (
        "history:1: user: é R$ 14,99\n"
        "history:2: user: quero contestar Tamboro Mensal"
    )
    out = await reconcile_transaction_parameters(
        llm,
        text="na verdade é Produto Inexistente",
        conversational_context=history,
        tool_name="contestar_cobranca",
        parameter_names=["subject", "valor"],
        known_arguments={"subject": "Tamboro Mensal", "valor": 14.99},
        parameter_schema={
            "subject": {"type": "string", "description": "Nome do serviço, produto, item ou cobrança objeto da contestação."},
            "valor": {"type": "number", "description": "Valor monetário associado ao item objeto da contestação."},
        },
        tool_description="Contesta uma cobrança após validação.",
    )
    # The newest candidate stays visible for pre-validation; the old product is not silently restored.
    assert out["values"] == {"subject": "Produto Inexistente"}
    assert "valor" in out["clear_fields"]
    assert "Tamboro Mensal" in llm.prompts[-1]  # history remains available to future reconciliation.


@pytest.mark.asyncio
async def test_temporal_reconciliation_can_restore_coherent_old_value_when_product_is_explicitly_restored():
    from agent_framework.runtime.transaction_parameters import reconcile_transaction_parameters

    llm = _CoherentTemporalLLM()
    out = await reconcile_transaction_parameters(
        llm,
        text="desculpa, era Tamboro Mensal mesmo",
        conversational_context=(
            "history:1: user: na verdade é Produto Inexistente\n"
            "history:2: user: é R$ 14,99\n"
            "history:3: user: quero contestar Tamboro Mensal"
        ),
        tool_name="contestar_cobranca",
        parameter_names=["subject", "valor"],
        known_arguments={},
        parameter_schema={
            "subject": {"type": "string", "description": "Nome do serviço, produto, item ou cobrança objeto da contestação."},
            "valor": {"type": "number", "description": "Valor monetário associado ao item objeto da contestação."},
        },
        tool_description="Contesta uma cobrança após validação.",
    )
    assert out["values"] == {"subject": "Tamboro Mensal", "valor": 14.99}
    assert out["provenance"] == {"subject": "current", "valor": "history:2"}


def test_temporal_context_priority_places_assistant_before_older_user_history():
    from agent_framework.runtime.agent_runtime import AgentRuntimeMixin

    context = (
        "user: tem uma cobrança aqui que eu não reconheço\n"
        "assistant: Cobrança Tamboro Mensal no valor de R$ 14,99; TIM Fashion Mensal no valor de R$ 10,00."
    )
    prioritized = AgentRuntimeMixin._transaction_context_priority_view(context)

    assert "priority_3_previous_assistant_tool_or_evidence_context:" in prioritized
    assert "priority_4_previous_user_utterances:" in prioritized
    assert prioritized.index("assistant: Cobrança Tamboro Mensal") < prioritized.index("user: tem uma cobrança")


class _AssistantRelationshipReconcilerLLM:
    def __init__(self):
        self.prompt = ""

    async def ainvoke(self, messages, **kwargs):
        self.prompt = messages[-1]["content"]
        # Simula o comportamento desejado: a fala atual dá o valor, enquanto a
        # relação item->valor está numa resposta anterior do assistant.
        assert "user_message: é a de quatorze e noventa e nove" in self.prompt
        assert "priority_3_previous_assistant_tool_or_evidence_context:" in self.prompt
        assert "assistant: Cobrança Tamboro Mensal no valor de R$ 14,99" in self.prompt
        assert "anchor_relation_candidates:" in self.prompt
        assert "anchor[valor=14.99]" in self.prompt
        return json.dumps({"fields": {
            "subject": {"decision": "resolved", "value": "Tamboro Mensal", "source": "history:1"},
            "valor": {"decision": "resolved", "value": 14.99, "source": "current"},
        }}, ensure_ascii=False)


@pytest.mark.asyncio
async def test_temporal_reconciler_can_use_grounded_assistant_relationship_after_current_only_extraction_is_incomplete():
    from agent_framework.runtime.agent_runtime import AgentRuntimeMixin

    class Runtime(AgentRuntimeMixin):
        pass

    runtime = Runtime()
    runtime.llm = _AssistantRelationshipReconcilerLLM()
    runtime.tool_router = type("TR", (), {
        "registry": type("REG", (), {
            "get_tool": staticmethod(lambda name: type("CFG", (), {
                "requires": ["subject", "valor"],
                "args_schema": {
                    "subject": {"type": "string", "description": "Nome do item ou cobrança a contestar."},
                    "valor": {"type": "number", "description": "Valor monetário do item a contestar."},
                },
                "description": "Contesta uma cobrança após validação.",
            })())
        })(),
        "resolve_execution_policy": staticmethod(lambda name, arguments=None: {
            "operation_type": "transactional",
            "requires": ["subject", "valor"],
        }),
    })()

    state = {
        "sanitized_input": "é a de quatorze e noventa e nove",
        "user_text": "é a de quatorze e noventa e nove",
        "route_decision": {"metadata": {
            "contextual_reentry": True,
            "original_input": "é a de quatorze e noventa e nove",
            "relevant_conversation_context": (
                "user: tem uma cobrança aqui que eu não reconheço\n"
                "assistant: Cobrança Tamboro Mensal no valor de R$ 14,99; TIM Fashion Mensal no valor de R$ 10,00."
            ),
        }},
    }

    # O happy path corrente só consegue o valor; o subject fica faltando.
    class _CurrentOnlyLLM:
        async def ainvoke(self, messages, **kwargs):
            return json.dumps({"valor": 14.99}, ensure_ascii=False)

    original_llm = runtime.llm
    runtime.llm = _CurrentOnlyLLM()
    current = await runtime._extract_transaction_parameters_current_only(
        state,
        tool_name="contestar_cobranca",
        missing_parameters=["subject", "valor"],
        known_arguments={},
    )
    assert current == {"valor": 14.99}

    runtime.llm = original_llm
    reconciled = await runtime._reconcile_transaction_parameters(
        state,
        tool_name="contestar_cobranca",
        parameter_names=["subject", "valor"],
        known_arguments=current,
    )
    assert reconciled["values"]["subject"] == "Tamboro Mensal"
    assert float(reconciled["values"]["valor"]) == 14.99
    assert "(3) respostas anteriores do assistente" in runtime.llm.prompt

class _UnifiedAnchorScanLLM:
    def __init__(self):
        self.calls = []

    async def ainvoke(self, messages, **kwargs):
        prompt = messages[-1]["content"]
        self.calls.append(prompt)
        assert "UMA ÚNICA VARREDURA TEMPORAL" in prompt
        assert "known_parameters: {\"valor\": 14.99}" in prompt
        assert "missing_parameters: [\"subject\", \"data\"]" in prompt
        assert "anchor_relation_candidates:" in prompt
        assert "anchor[valor=14.99]" in prompt
        assert "Tamboro Mensal no valor de R$ 14,99" in prompt
        return json.dumps({"fields": {
            "subject": {"decision": "resolved", "value": "Tamboro Mensal", "source": "history:1"},
            "valor": {"decision": "preserve", "value": None, "source": "state"},
            "data": {"decision": "resolved", "value": "01/11/2025", "source": "history:1"},
        }}, ensure_ascii=False)


@pytest.mark.asyncio
async def test_temporal_reconciler_single_scan_uses_all_known_fields_as_anchors_and_resolves_all_missing_fields():
    from agent_framework.runtime.transaction_parameters import reconcile_transaction_parameters

    llm = _UnifiedAnchorScanLLM()
    result = await reconcile_transaction_parameters(
        llm,
        text="é a de quatorze e noventa e nove",
        tool_name="contestar_cobranca",
        parameter_names=["subject", "valor", "data"],
        known_arguments={"valor": 14.99},
        parameter_schema={
            "subject": {"type": "string", "description": "Nome do item ou cobrança a contestar."},
            "valor": {"type": "number", "description": "Valor monetário do item a contestar."},
            "data": {"type": "string", "description": "Data da cobrança selecionada."},
        },
        tool_description="Contesta uma cobrança após validação.",
        conversational_context=(
            "priority_3_previous_assistant_tool_or_evidence_context:\n"
            "history:1: assistant: Cobrança Tamboro Mensal no valor de R$ 14,99 no dia 01/11/2025 * "
            "TIM Fashion Mensal no valor de R$ 10,00 no dia 01/11/2025.\n"
            "priority_4_previous_user_utterances:\n"
            "history:2: user: tem uma cobrança aqui que eu não reconheço"
        ),
    )

    assert len(llm.calls) == 1
    assert result["values"]["subject"] == "Tamboro Mensal"
    assert float(result["values"]["valor"]) == 14.99
    assert result["values"]["data"] == "01/11/2025"
    assert result["provenance"]["subject"] == "history:1"


class _AssistantEvidenceSegmentationLLM:
    def __init__(self):
        self.calls = 0

    async def ainvoke(self, messages, **kwargs):
        import json
        self.calls += 1
        prompt = messages[-1]["content"]
        evidence = json.loads(prompt.split("evidence_blocks: ", 1)[1].split("\n", 1)[0])
        anchored = [
            block for block in evidence
            if block.get("role") == "assistant"
            and any(match.get("field") == "valor" and float(match.get("value")) == 14.99 for match in block.get("anchor_matches", []))
        ]
        assert len(anchored) == 1
        assert "Tamboro Mensal" in anchored[0]["text"]
        assert "TIM Fashion" not in anchored[0]["text"]
        assert "Neymar" not in anchored[0]["text"]
        return {
            "content": json.dumps({
                "fields": {
                    "subject": {"decision": "resolved", "value": "Tamboro Mensal", "source": "history:1"},
                    "valor": {"decision": "preserve", "value": 14.99, "source": "state"},
                }
            }, ensure_ascii=False)
        }


@pytest.mark.asyncio
async def test_reconciler_segments_assistant_list_so_known_anchor_resolves_missing_field():
    llm = _AssistantEvidenceSegmentationLLM()
    result = await reconcile_transaction_parameters(
        llm,
        text="é a de quatorze e noventa e nove",
        tool_name="contestar_cobranca",
        parameter_names=["subject", "valor"],
        known_arguments={"valor": 14.99},
        parameter_schema={
            "subject": {"type": "string", "description": "Nome do item ou cobrança a contestar."},
            "valor": {"type": "number", "description": "Valor monetário do item a contestar."},
        },
        conversational_context=(
            "priority_3_previous_assistant_tool_or_evidence_context:\n"
            "history:1: assistant: Houve as cobranças: * Cobrança Tamboro Mensal no valor de R$ 14,99 no dia 01/11/25. "
            "* Cobrança TIM Fashion Mensal no valor de R$ 10,00 no dia 01/11/25. "
            "* Cobrança Neymar Jr no valor de R$ 12,00 no dia 01/11/25.\n"
            "priority_4_previous_user_utterances:\n"
            "history:2: user: tem uma cobrança aqui que eu não reconheço"
        ),
    )
    assert llm.calls == 1
    assert result["values"]["subject"] == "Tamboro Mensal"
    assert float(result["values"]["valor"]) == 14.99
