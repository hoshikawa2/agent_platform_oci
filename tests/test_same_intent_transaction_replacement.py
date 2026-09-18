import json
from types import SimpleNamespace

import pytest

from agent_framework.routing.enterprise_router import EnterpriseRouter
from agent_framework.runtime.agent_runtime import AgentRuntimeMixin


class _ReplacementLLM:
    async def ainvoke(self, messages, **kwargs):
        system = str(messages[0].get("content") if isinstance(messages[0], dict) else messages[0]).lower()
        user = str(messages[-1].get("content") if isinstance(messages[-1], dict) else messages[-1]).lower()

        # First probe is abandonment-only and must not steal a normal same-intent replacement.
        if "somente se o usuário desistiu explicitamente" in system:
            if "esquece" in user:
                return json.dumps({
                    "decision": "ABANDON",
                    "intent": "contas_vas_cancel",
                    "agent": "contestacao_agent",
                    "confidence": 0.99,
                    "reason": "abandona a instância anterior e inicia novo cancelamento",
                })
            return json.dumps({
                "decision": "CONTINUE",
                "intent": None,
                "agent": None,
                "confidence": 0.99,
                "reason": "não houve abandono explícito",
            })

        if "também tim fashion" in user or "tambem tim fashion" in user:
            return json.dumps({
                "decision": "CONTINUE",
                "intent": "contas_vas_cancel",
                "agent": "contestacao_agent",
                "confidence": 0.99,
                "reason": "adição de item à mesma operação, não substituição",
            })

        return json.dumps({
            "decision": "REPLACE",
            "intent": "contas_vas_cancel",
            "agent": "contestacao_agent",
            "confidence": 0.99,
            "reason": "mesma intenção, novo alvo transacional",
        })


def _router(tmp_path):
    routing = tmp_path / "routing.yaml"
    routing.write_text(
        """
router:
  fallback_agent: contestacao_agent
  confidence_threshold: 0.70
state_policies:
  - state: WAITING_CONTESTACAO_CONFIRMATION
    agent: contestacao_agent
intents:
  - name: contas_vas_cancel
    domain: telecom_contas
    agent: contestacao_agent
    priority: 20
    keywords: [cancelar]
    mcp_tools: [consultar_vas, cancelar_vas_avulso]
""",
        encoding="utf-8",
    )
    return EnterpriseRouter(
        SimpleNamespace(
            ROUTING_CONFIG_PATH=str(routing),
            ENABLE_LLM_ROUTER=True,
            ENABLE_ROUTE_STICKINESS=False,
        ),
        llm=_ReplacementLLM(),
    )


def _state(message):
    return {
        "user_text": message,
        "sanitized_input": message,
        "next_state": "WAITING_CONTESTACAO_CONFIRMATION",
        "transaction_status": "AWAITING_CONFIRMATION",
        "intent": "state:WAITING_CONTESTACAO_CONFIRMATION",
        "active_agent": "contestacao_agent",
        "active_transaction": {
            "tool_name": "cancelar_vas_avulso",
            "arguments": {"subject": ["Tamboro Mensal", "Paramount+"]},
            "status": "AWAITING_CONFIRMATION",
            "started_from_intent": "contas_vas_cancel",
        },
        "pending_tool_call": {
            "tool_name": "cancelar_vas_avulso",
            "arguments": {"subject": ["Tamboro Mensal", "Paramount+"]},
        },
    }


@pytest.mark.asyncio
async def test_same_intent_new_target_emits_replacement_without_new_state(tmp_path):
    decision = await _router(tmp_path).route(_state("quero cancelar TIM Fashion"))

    assert decision.intent == "contas_vas_cancel"
    assert decision.agent == "contestacao_agent"
    assert decision.next_state is None
    assert decision.metadata["transaction_interruption"] == "same_intent_replacement"
    assert decision.metadata["interrupted_intent"] == "contas_vas_cancel"


@pytest.mark.asyncio
async def test_same_intent_additive_request_keeps_current_transaction(tmp_path):
    decision = await _router(tmp_path).route(_state("quero cancelar também TIM Fashion"))

    assert decision.method == "state"
    assert decision.intent == "state:WAITING_CONTESTACAO_CONFIRMATION"
    assert "transaction_interruption" not in (decision.metadata or {})


@pytest.mark.asyncio
async def test_explicit_abandonment_with_same_intent_new_target_can_preempt_state_lock(tmp_path):
    decision = await _router(tmp_path).route(_state("esquece, quero cancelar TIM Fashion"))

    assert decision.intent == "contas_vas_cancel"
    assert decision.agent == "contestacao_agent"
    assert decision.metadata["transaction_interruption"] == "explicit_abandonment"


@pytest.mark.asyncio
async def test_runtime_cancels_old_instance_for_same_intent_replacement():
    runtime = AgentRuntimeMixin()
    state = {
        "sanitized_input": "quero cancelar TIM Fashion",
        "user_text": "quero cancelar TIM Fashion",
        "route_decision": {
            "metadata": {"transaction_interruption": "same_intent_replacement"}
        },
        "active_transaction": {
            "tool_name": "cancelar_vas_avulso",
            "arguments": {"subject": ["Tamboro Mensal", "Paramount+"]},
            "status": "AWAITING_CONFIRMATION",
            "started_from_intent": "contas_vas_cancel",
        },
        "pending_tool_call": {
            "tool_name": "cancelar_vas_avulso",
            "arguments": {"subject": ["Tamboro Mensal", "Paramount+"]},
        },
        "selected_tool_call": {
            "tool_name": "cancelar_vas_avulso",
            "arguments": {"subject": ["Tamboro Mensal", "Paramount+"]},
        },
        "transaction_status": "AWAITING_CONFIRMATION",
        "mcp_tools": [],
    }

    await runtime.execute_tools_for_intent(state, tools=[])

    assert state.get("active_transaction") is None
    assert state.get("pending_tool_call") in ({}, None)
    assert state.get("selected_tool_call") in ({}, None)
    assert state["tool_policy_result"]["action"] == "cancelled_by_same_intent_replacement"
    assert state["operational_context_reset"] is True
