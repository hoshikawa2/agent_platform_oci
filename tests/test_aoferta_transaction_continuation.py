import pytest

from agent_framework.guardrails.rails import ProactiveOfferRail


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["COLLECTING_PARAMETERS", "AWAITING_CONFIRMATION"])
async def test_aoferta_bypasses_transaction_continuation_without_llm(monkeypatch, status):
    async def should_not_run(*args, **kwargs):
        raise AssertionError("AOFERTA LLM must not run for transaction continuation")

    monkeypatch.setattr(
        "agent_framework.guardrails.rails.classify_with_framework_llm",
        should_not_run,
    )

    decision = await ProactiveOfferRail().evaluate(
        "Para prosseguir, informe valor.",
        {"transaction_status": status},
    )

    assert decision.allowed is True
    assert decision.code == "AOFERTA"
    assert decision.metadata["mechanism"] == "deterministic_transaction_bypass"
    assert decision.metadata["transaction_status"] == status


@pytest.mark.asyncio
async def test_aoferta_detects_transaction_continuation_from_mcp_results(monkeypatch):
    async def should_not_run(*args, **kwargs):
        raise AssertionError("AOFERTA LLM must not run for transaction continuation")

    monkeypatch.setattr(
        "agent_framework.guardrails.rails.classify_with_framework_llm",
        should_not_run,
    )

    decision = await ProactiveOfferRail().evaluate(
        "Você confirma o cancelamento do serviço TIM Fashion?",
        {
            "mcp_results": [
                {
                    "tool_name": "cancelar_vas_avulso",
                    "awaiting_confirmation": True,
                    "transaction_status": "AWAITING_CONFIRMATION",
                }
            ]
        },
    )

    assert decision.allowed is True
    assert decision.metadata["transaction_status"] == "AWAITING_CONFIRMATION"


@pytest.mark.asyncio
async def test_aoferta_still_calls_llm_outside_transaction_continuation(monkeypatch):
    calls = []

    async def fake_classify(*args, **kwargs):
        calls.append((args, kwargs))
        return {"allowed": False, "reason": "oferta proativa"}

    monkeypatch.setattr(
        "agent_framework.guardrails.rails.classify_with_framework_llm",
        fake_classify,
    )

    decision = await ProactiveOfferRail().evaluate(
        "Quer aproveitar e cancelar outro serviço?",
        {"transaction_status": "COMPLETED"},
    )

    assert len(calls) == 1
    assert decision.allowed is False
    assert decision.metadata["mechanism"] == "llm_supervisor"
