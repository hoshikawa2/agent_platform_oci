from types import SimpleNamespace

import pytest

from agent_framework.routing.enterprise_router import EnterpriseRouter
from agent_framework.runtime.agent_runtime import AgentRuntimeMixin
from agent_framework.workflows.input_contract import match_expected_input


ROUTING_YAML = """
router:
  fallback_agent: billing_agent
  confidence_threshold: 0.70
intents:
  - name: billing_invoice_explanation
    domain: telecom
    agent: faturas_agent
    priority: 40
    keywords: [fatura]
"""


class _ContinuityLLM:
    async def ainvoke(self, messages, **kwargs):
        if kwargs.get("profile_name") == "route_continuity":
            return '{"decision":"END_SESSION","confidence":0.99,"reason":"sim"}'
        return '{}'


def _router(tmp_path):
    routing = tmp_path / "routing.yaml"
    routing.write_text(ROUTING_YAML, encoding="utf-8")
    settings = SimpleNamespace(
        ROUTING_CONFIG_PATH=str(routing),
        ENABLE_LLM_ROUTER=False,
        ENABLE_ROUTE_STICKINESS=True,
        ROUTE_STICKINESS_LLM_PROFILE="route_continuity",
        ROUTE_STICKINESS_CONFIDENCE_THRESHOLD=0.7,
    )
    return EnterpriseRouter(settings, llm=_ContinuityLLM())


def _workflow_result():
    return {
        "result": {
            "result": {
                "status": "PAUSED",
                "execution_id": "exec-1",
                "workflow_name": "invoice_explanation",
                "metadata": {
                    "workflow_name": "invoice_explanation",
                    "workflow_execution_id": "exec-1",
                    "resume_tool": "retomar_workflow",
                },
                "pause": {"node": "formatar"},
                "state": {
                    "__interrupt__": [
                        {
                            "value": {
                                "node": "formatar",
                                "prompt": "Sanei sua dúvida?",
                                "expected_input": {
                                    "key": "resposta_usuario",
                                    "allowed_values": ["SIM", "NAO"],
                                    "normalize": "upper_strip",
                                },
                                "resume_from": "decisao",
                            },
                            "id": "interrupt-1",
                        }
                    ]
                },
            }
        }
    }


class _Runtime(AgentRuntimeMixin):
    async def _call_mcp_tool(self, tool_name, arguments, state):
        self.called = (tool_name, arguments)
        return {
            "result": {
                "result": {
                    "status": "COMPLETED",
                    "execution_id": arguments["execution_id"],
                    "workflow_name": arguments["workflow_name"],
                    "metadata": {"workflow_name": arguments["workflow_name"]},
                }
            }
        }


def test_capture_recovers_expected_input_from_interrupt_descriptor():
    runtime = _Runtime()
    state = {"route": "faturas_agent", "active_agent": "faturas_agent", "intent": "billing_invoice_explanation"}
    runtime._capture_pending_domain_workflow(state, _workflow_result())
    pending = state["pending_domain_workflow"]
    assert pending["owner_agent"] == "faturas_agent"
    assert pending["pause"]["expected_input"]["allowed_values"] == ["SIM", "NAO"]
    assert pending["pause"]["resume_from"] == "decisao"


def test_expected_input_contract_is_deterministic():
    contract = {"allowed_values": ["SIM", "NAO"], "normalize": "upper_strip"}
    assert match_expected_input(" sim ", contract) == "SIM"
    assert match_expected_input("não", contract) is None
    assert match_expected_input("quero minha fatura", contract) is None


@pytest.mark.asyncio
async def test_paused_workflow_expected_input_preempts_route_continuity(tmp_path):
    router = _router(tmp_path)
    state = {
        "user_text": "sim",
        "sanitized_input": "sim",
        "route": "faturas_agent",
        "active_agent": "faturas_agent",
        "intent": "billing_invoice_explanation",
        "route_decision": {
            "route": "faturas_agent",
            "agent": "faturas_agent",
            "intent": "billing_invoice_explanation",
            "domain": "telecom",
        },
        "pending_domain_workflow": {
            "workflow_name": "invoice_explanation",
            "execution_id": "exec-1",
            "resume_tool": "retomar_workflow",
            "owner_agent": "faturas_agent",
            "owner_intent": "billing_invoice_explanation",
            "pause": {
                "expected_input": {
                    "key": "resposta_usuario",
                    "allowed_values": ["SIM", "NAO"],
                    "normalize": "upper_strip",
                }
            },
        },
    }
    decision = await router.route(state)
    assert decision.method == "state"
    assert decision.metadata["workflow_resume"] is True
    assert decision.route == "faturas_agent"
    assert decision.mcp_tools == ["retomar_workflow"]
    assert decision.metadata["normalized_input"] == "SIM"


@pytest.mark.asyncio
async def test_runtime_resume_uses_contract_normalized_value():
    runtime = _Runtime()
    state = {
        "pending_domain_workflow": {
            "workflow_name": "invoice_explanation",
            "execution_id": "exec-1",
            "resume_tool": "retomar_workflow",
            "pause": {
                "expected_input": {
                    "key": "resposta_usuario",
                    "allowed_values": ["SIM", "NAO"],
                    "normalize": "upper_strip",
                }
            },
        },
        "transaction_status": "WORKFLOW_PAUSED",
    }
    result = await runtime._resume_pending_domain_workflow(state, " sim ")
    assert result is not None
    assert runtime.called[0] == "retomar_workflow"
    assert runtime.called[1]["resposta_usuario"] == "SIM"
    assert state["pending_domain_workflow"] is None


def test_terminal_workflow_capture_materializes_latch_clear_for_graph_merge():
    runtime = _Runtime()
    state = {
        "pending_domain_workflow": {
            "workflow_name": "invoice_explanation",
            "execution_id": "exec-1",
            "resume_tool": "retomar_workflow",
        },
        "transaction_status": "WORKFLOW_PAUSED",
    }
    runtime._capture_pending_domain_workflow(
        state,
        {
            "result": {
                "result": {
                    "status": "COMPLETED",
                    "execution_id": "exec-1",
                    "workflow_name": "invoice_explanation",
                    "metadata": {
                        "workflow_name": "invoice_explanation",
                        "workflow_execution_id": "exec-1",
                    },
                }
            }
        },
    )
    assert state["pending_domain_workflow"] is None
    assert state["transaction_status"] is None
    patch = runtime.transaction_state_patch(state)
    assert "pending_domain_workflow" in patch
    assert patch["pending_domain_workflow"] is None


def test_terminal_workflow_does_not_clear_different_pending_execution():
    runtime = _Runtime()
    pending = {
        "workflow_name": "other_workflow",
        "execution_id": "exec-other",
        "resume_tool": "retomar_workflow",
    }
    state = {"pending_domain_workflow": dict(pending), "transaction_status": "WORKFLOW_PAUSED"}
    runtime._capture_pending_domain_workflow(
        state,
        {
            "result": {
                "result": {
                    "status": "COMPLETED",
                    "execution_id": "exec-1",
                    "workflow_name": "invoice_explanation",
                    "metadata": {
                        "workflow_name": "invoice_explanation",
                        "workflow_execution_id": "exec-1",
                    },
                }
            }
        },
    )
    assert state["pending_domain_workflow"] == pending
    assert state["transaction_status"] == "WORKFLOW_PAUSED"


def test_route_shift_clears_paused_workflow_and_live_latches_without_touching_history():
    runtime = _Runtime()
    state = {
        "route": "new_agent",
        "intent": "new_intent",
        "route_decision": {
            "route": "new_agent",
            "agent": "new_agent",
            "intent": "new_intent",
            "metadata": {},
        },
        "pending_domain_workflow": {
            "workflow_name": "old_workflow",
            "execution_id": "exec-old",
            "resume_tool": "resume_old",
            "owner_agent": "old_agent",
            "owner_intent": "old_intent",
            "pause": {"expected_input": {"allowed_values": ["YES", "NO"]}},
        },
        "transaction_status": "WORKFLOW_PAUSED",
        "selected_tool_call": {"tool_name": "old_tool", "arguments": {"x": 1}},
        "pending_tool_call": {"tool_name": "old_tool", "arguments": {"x": 1}},
        "missing_parameters": ["x"],
        "confirmation_required": True,
        "confirmation_received": True,
        "next_state": "OLD_STATE",
        "transaction_pre_validation": {"eligible": True},
        "pending_tool_clarification": {"tool_name": "old_tool"},
        "mcp_results": [{"tool_name": "resume_old", "ok": False}],
        "business_workflows_executed": ["historical_workflow"],
    }

    changed = runtime._clear_active_interaction_context_on_route_shift(state)

    assert changed is True
    assert state["pending_domain_workflow"] is None
    assert state["transaction_status"] is None
    assert state["selected_tool_call"] == {}
    assert state["pending_tool_call"] == {}
    assert state["missing_parameters"] == []
    assert state["confirmation_required"] is False
    assert state["confirmation_received"] is False
    assert state["next_state"] is None
    assert state["transaction_pre_validation"] is None
    assert state["pending_tool_clarification"] is None
    assert state["mcp_results"] == []
    assert state["business_workflows_executed"] == ["historical_workflow"]
    assert state["last_interrupted_domain_workflow"]["execution_id"] == "exec-old"
    assert state["last_interrupted_domain_workflow"]["reason"] == "intent_shift"


def test_workflow_resume_does_not_clear_paused_workflow():
    runtime = _Runtime()
    pending = {
        "workflow_name": "wf",
        "execution_id": "exec-1",
        "owner_agent": "agent-a",
        "owner_intent": "intent-a",
    }
    state = {
        "route": "agent-a",
        "intent": "intent-a",
        "route_decision": {
            "route": "agent-a",
            "agent": "agent-a",
            "intent": "intent-a",
            "metadata": {"workflow_resume": True},
        },
        "pending_domain_workflow": dict(pending),
        "transaction_status": "WORKFLOW_PAUSED",
        "mcp_results": [{"tool_name": "something"}],
    }

    changed = runtime._clear_active_interaction_context_on_route_shift(state)

    assert changed is False
    assert state["pending_domain_workflow"] == pending
    assert state["transaction_status"] == "WORKFLOW_PAUSED"
    assert state["mcp_results"] == [{"tool_name": "something"}]


def test_same_workflow_owner_without_resume_does_not_get_cleared_as_intent_shift():
    runtime = _Runtime()
    pending = {
        "workflow_name": "wf",
        "execution_id": "exec-1",
        "owner_agent": "agent-a",
        "owner_intent": "intent-a",
    }
    state = {
        "route": "agent-a",
        "intent": "intent-a",
        "route_decision": {
            "route": "agent-a",
            "agent": "agent-a",
            "intent": "intent-a",
            "metadata": {},
        },
        "pending_domain_workflow": dict(pending),
        "transaction_status": "WORKFLOW_PAUSED",
    }
    assert runtime._clear_active_interaction_context_on_route_shift(state) is False
    assert state["pending_domain_workflow"] == pending
