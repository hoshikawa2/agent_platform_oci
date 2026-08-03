from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agent_framework.routing.continuity import SemanticRouteContinuity
from agent_framework.routing.models import IntentDefinition


class FakeLLM:
    def __init__(self, response: dict | str):
        self.response = response
        self.calls = []

    async def ainvoke(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if isinstance(self.response, str):
            return self.response
        return json.dumps(self.response)


class FakeTelemetry:
    def __init__(self):
        self.events = []

    async def event(self, name, payload):
        self.events.append((name, payload))


def settings(**overrides):
    values = {
        "ENABLE_ROUTE_STICKINESS": True,
        "ROUTE_STICKINESS_LLM_PROFILE": "route_continuity",
        "ROUTE_STICKINESS_CONFIDENCE_THRESHOLD": 0.90,
        "ROUTE_STICKINESS_HISTORY_TURNS": 2,
        "ROUTE_STICKINESS_MAX_TOKENS": 80,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def intents():
    return [
        IntentDefinition(
            name="product_services_information",
            agent="product_agent",
            description="Planos, serviços, benefícios e mudança de plano.",
        ),
        IntentDefinition(
            name="billing_invoice_explanation",
            agent="billing_agent",
            description="Faturas, pagamentos, cobranças e contestação.",
        ),
    ]


def state(message="o que está incluso?"):
    return {
        "session_id": "s1",
        "active_agent": "product_agent",
        "intent": "product_services_information",
        "domain": "telecom",
        "route_decision": {
            "intent": "product_services_information",
            "domain": "telecom",
            "mcp_tools": ["consultar_plano"],
        },
        "history": [
            {"role": "user", "content": "qual é o meu plano?"},
            {"role": "assistant", "content": "Seu plano atual é Controle 50GB."},
        ],
        "user_text": message,
        "sanitized_input": message,
    }


@pytest.mark.asyncio
async def test_continue_bypasses_router_without_regex_rules():
    llm = FakeLLM({"decision": "CONTINUE", "confidence": 0.97, "reason": "Continua o assunto do plano."})
    telemetry = FakeTelemetry()
    policy = SemanticRouteContinuity(settings(), llm, telemetry)

    decision = await policy.evaluate(state(), intents=intents())

    assert decision is not None
    assert decision.agent == "product_agent"
    assert decision.method == "continuity"
    assert decision.metadata["route_bypassed"] is True
    assert llm.calls[0][1]["profile_name"] == "route_continuity"
    prompt = json.loads(llm.calls[0][0][1]["content"])
    assert prompt["current_message"] == "o que está incluso?"
    assert "product_agent" not in prompt["other_agents"]
    assert telemetry.events[-1][1]["route_bypassed"] is True


@pytest.mark.asyncio
async def test_route_result_falls_back_to_enterprise_router():
    llm = FakeLLM({"decision": "ROUTE", "confidence": 0.98, "reason": "Novo assunto de cobrança."})
    policy = SemanticRouteContinuity(settings(), llm)

    decision = await policy.evaluate(
        state("agora quero contestar uma cobrança"), intents=intents()
    )

    assert decision is None


@pytest.mark.asyncio
async def test_low_confidence_continue_falls_back_safely():
    llm = FakeLLM({"decision": "CONTINUE", "confidence": 0.70, "reason": "Possível continuidade."})
    policy = SemanticRouteContinuity(settings(), llm)

    assert await policy.evaluate(state(), intents=intents()) is None


@pytest.mark.asyncio
async def test_invalid_output_falls_back_safely():
    llm = FakeLLM("not-json")
    policy = SemanticRouteContinuity(settings(), llm)

    assert await policy.evaluate(state(), intents=intents()) is None


@pytest.mark.asyncio
async def test_no_active_agent_still_classifies_global_session_actions():
    llm = FakeLLM({"decision": "ROUTE", "confidence": 1.0})
    policy = SemanticRouteContinuity(settings(), llm)
    current = state()
    current.pop("active_agent")

    assert await policy.evaluate(current, intents=intents()) is None
    assert len(llm.calls) == 1

@pytest.mark.asyncio
async def test_human_handoff_is_returned_as_global_route():
    llm = FakeLLM({
        "decision": "HUMAN_HANDOFF",
        "confidence": 0.99,
        "reason": "O usuário pediu atendimento humano.",
    })
    policy = SemanticRouteContinuity(settings(), llm)

    decision = await policy.evaluate(
        state("quero falar com um atendente"), intents=intents()
    )

    assert decision is not None
    assert decision.route == "human_handoff"
    assert decision.agent == "human_handoff"
    assert decision.intent == "human_handoff"
    assert decision.handoff is True
    assert decision.metadata["session_control"] == "HUMAN_HANDOFF"
    assert decision.metadata["route_bypassed"] is True


@pytest.mark.asyncio
async def test_end_session_is_returned_as_global_route():
    llm = FakeLLM({
        "decision": "END_SESSION",
        "confidence": 0.98,
        "reason": "O usuário informou que não precisa continuar.",
    })
    policy = SemanticRouteContinuity(settings(), llm)

    decision = await policy.evaluate(state("obrigado, era só isso"), intents=intents())

    assert decision is not None
    assert decision.route == "end_session"
    assert decision.agent == "end_session"
    assert decision.intent == "end_session"
    assert decision.handoff is False
    assert decision.metadata["session_control"] == "END_SESSION"
    assert decision.metadata["route_bypassed"] is True


@pytest.mark.asyncio
async def test_global_session_actions_work_without_active_agent():
    llm = FakeLLM({
        "decision": "HUMAN_HANDOFF",
        "confidence": 0.97,
        "reason": "Solicitação explícita de pessoa.",
    })
    policy = SemanticRouteContinuity(settings(), llm)
    current = state("quero uma pessoa")
    current.pop("active_agent")

    decision = await policy.evaluate(current, intents=intents())

    assert decision is not None
    assert decision.route == "human_handoff"
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_continue_without_active_agent_falls_back_to_router():
    llm = FakeLLM({"decision": "CONTINUE", "confidence": 0.99})
    policy = SemanticRouteContinuity(settings(), llm)
    current = state()
    current.pop("active_agent")

    assert await policy.evaluate(current, intents=intents()) is None
    assert len(llm.calls) == 1
