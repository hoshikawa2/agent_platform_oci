from __future__ import annotations

import json
import pytest

from agent_framework.runtime.transaction_parameters import extract_transaction_parameters


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
