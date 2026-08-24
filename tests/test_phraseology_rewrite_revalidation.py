import pytest

from agent_framework.guardrails.base import RailDecision
from agent_framework.guardrails.output_supervisor import OutputSupervisor
from agent_framework.guardrails.rail_action import RailAction


class PhraseologyRail:
    code = "FRASEOLOGIA"
    stage = "output"

    def __init__(self):
        self.calls = []

    async def evaluate(self, text, context):
        self.calls.append(text)
        blocked = "categoria tratável por esta operação" in text
        return RailDecision(
            code=self.code,
            allowed=not blocked,
            reason=(
                "remova linguagem interna" if blocked else ""
            ),
            sanitized_text=text,
            metadata={"calibrated": True, "remediation": {"type": "rewrite", "max_attempts": 1, "prompt_id": "FALLBACK"}},
        )


class AllowRail:
    code = "AOFERTA"
    stage = "output"

    def __init__(self):
        self.calls = []

    async def evaluate(self, text, context):
        self.calls.append(text)
        return RailDecision(
            code=self.code,
            allowed=True,
            reason="",
            sanitized_text=text,
            metadata={"calibrated": True},
        )


@pytest.mark.asyncio
async def test_phraseology_block_is_rewritten_once_and_all_rails_are_revalidated(monkeypatch):
    phrase = PhraseologyRail()
    allow = AllowRail()

    async def fake_classify(llm, task, payload, **kwargs):
        assert task == "FALLBACK"
        assert payload["context"]["guardrail_code"] == "FRASEOLOGIA"
        return {
            "allowed": True,
            "label": "FALLBACK",
            "reason": (
                '[ContestacaoAgent] O item "TIM CTRL Redes Sociais 8.0" no valor de '
                'R$ 71,99 é um plano da sua fatura e, por isso, não pode ser '
                'contestado como serviço adicional.'
            ),
        }

    monkeypatch.setattr(
        "agent_framework.guardrails.output_supervisor.classify_with_framework_llm",
        fake_classify,
    )

    supervisor = OutputSupervisor(
        rails=[allow, phrase],
        enable_parallel=False,
        llm=object(),
    )
    original = (
        '[ContestacaoAgent] O item "TIM CTRL Redes Sociais 8.0" no valor de '
        'R$ 71,99 é classificado como plano na sua fatura. Não é possível '
        'contestar esse tipo de cobrança por este canal, pois planos não pertencem '
        'a uma categoria tratável por esta operação.'
    )

    decision = await supervisor.evaluate(original, {})

    assert decision.action in {RailAction.ALLOW, RailAction.SANITIZE, RailAction.OBSERVE}
    assert "categoria tratável por esta operação" not in decision.candidate
    assert "TIM CTRL Redes Sociais 8.0" in decision.candidate
    assert "R$ 71,99" in decision.candidate
    assert len(phrase.calls) == 2
    assert len(allow.calls) == 2
    assert decision.metadata["guardrail_rewritten"] is True
    assert any(r.code == "FRASEOLOGIA_REWRITE" for r in decision.results)


@pytest.mark.asyncio
async def test_phraseology_rewrite_does_not_loop_when_rewritten_text_is_still_blocked(monkeypatch):
    phrase = PhraseologyRail()

    async def fake_classify(llm, task, payload, **kwargs):
        return {
            "allowed": True,
            "label": "FALLBACK",
            "reason": payload["text"] + " ",
        }

    monkeypatch.setattr(
        "agent_framework.guardrails.output_supervisor.classify_with_framework_llm",
        fake_classify,
    )
    supervisor = OutputSupervisor(rails=[phrase], enable_parallel=False, llm=object())
    original = "planos não pertencem a uma categoria tratável por esta operação"

    decision = await supervisor.evaluate(original, {})
    assert decision.action == RailAction.BLOCK
    assert len(phrase.calls) == 1
