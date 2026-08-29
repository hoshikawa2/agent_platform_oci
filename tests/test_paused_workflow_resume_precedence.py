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
    assert state["transaction_status"] == "COMPLETED"


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
    assert state["transaction_status"] == "COMPLETED"
    assert state.get("active_transaction") is None
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


@pytest.mark.asyncio
async def test_terminal_status_treats_next_turn_as_new_interaction_same_session(tmp_path):
    router = _router(tmp_path)
    session_id = "same-session-22"
    state = {
        "user_text": "ah espera",
        "sanitized_input": "ah espera",
        "session_id": session_id,
        "transaction_status": "COMPLETED",
        # Simulate a stale pre-fix checkpoint. Terminal status must win.
        "pending_domain_workflow": {
            "workflow_name": "invoice_explanation",
            "execution_id": "exec-old",
            "resume_tool": "retomar_workflow",
            "owner_agent": "faturas_agent",
            "owner_intent": "billing_invoice_explanation",
            "pause": {
                "expected_input": {
                    "key": "resposta_usuario",
                    "allowed_values": ["SIM", "NAO", "CONTINUAR"],
                    "normalize": "upper_strip",
                }
            },
        },
    }
    decision = await router.route(state)
    assert state["session_id"] == session_id
    assert state["pending_domain_workflow"] is None
    assert not (decision.metadata or {}).get("workflow_resume")


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

@pytest.mark.asyncio
async def test_invalid_enumerated_workflow_input_keeps_workflow_ownership_and_reprompts(tmp_path):
    router = _router(tmp_path)
    state = {
        "user_text": "ano",
        "sanitized_input": "ano",
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
                "prompt": "Sanei sua dúvida?",
                "expected_input": {
                    "key": "resposta_usuario",
                    "allowed_values": ["SIM", "NAO"],
                    "normalize": "upper_strip",
                    "reprompt": "Não entendi. Essa explicação resolveu sua dúvida? Responda sim ou não.",
                },
            },
        },
    }
    decision = await router.route(state)
    assert decision.route == "faturas_agent"
    assert decision.method == "state"
    assert decision.mcp_tools == []
    assert decision.metadata["workflow_input_invalid"] is True
    assert decision.metadata["workflow_reprompt"] == (
        "Não entendi. Essa explicação resolveu sua dúvida? Responda sim ou não."
    )


@pytest.mark.asyncio
async def test_invalid_workflow_input_does_not_call_resume_tool_and_returns_reprompt():
    runtime = _Runtime()
    pending = {
        "workflow_name": "invoice_explanation",
        "execution_id": "exec-1",
        "resume_tool": "retomar_workflow",
        "owner_agent": "faturas_agent",
        "owner_intent": "billing_invoice_explanation",
        "pause": {
            "prompt": "Sanei sua dúvida?",
            "expected_input": {
                "key": "resposta_usuario",
                "allowed_values": ["SIM", "NAO"],
                "normalize": "upper_strip",
                "reprompt": "Não entendi. Essa explicação resolveu sua dúvida? Responda sim ou não.",
            },
        },
    }
    state = {
        "sanitized_input": "ano",
        "user_text": "ano",
        "route": "faturas_agent",
        "active_agent": "faturas_agent",
        "intent": "billing_invoice_explanation",
        "pending_domain_workflow": dict(pending),
        "transaction_status": "WORKFLOW_PAUSED",
        "route_decision": {
            "route": "faturas_agent",
            "agent": "faturas_agent",
            "intent": "billing_invoice_explanation",
            "metadata": {
                "workflow_input_invalid": True,
                "workflow_reprompt": "Não entendi. Essa explicação resolveu sua dúvida? Responda sim ou não.",
            },
        },
        "mcp_tools": [],
    }
    results = await runtime.execute_tools_for_intent(state)
    assert results == []
    assert not hasattr(runtime, "called")
    assert state["pending_domain_workflow"] == pending
    assert state["transaction_status"] == "WORKFLOW_PAUSED"
    assert runtime.transaction_clarification_message(state) == (
        "Não entendi. Essa explicação resolveu sua dúvida? Responda sim ou não."
    )


@pytest.mark.asyncio
async def test_meaningful_unmatched_workflow_input_resumes_as_declared_value(tmp_path):
    router = _router(tmp_path)
    state = {
        "user_text": "então tirando esses serviços o valor será 275, certo?",
        "sanitized_input": "então tirando esses serviços o valor será 275, certo?",
        "route": "faturas_agent",
        "active_agent": "faturas_agent",
        "intent": "billing_invoice_explanation",
        "route_decision": {
            "route": "faturas_agent",
            "agent": "faturas_agent",
            "intent": "billing_invoice_explanation",
            "domain": "telecom",
        },
        "guardrail_decisions": [
            {
                "code": "COER",
                "allowed": True,
                "metadata": {
                    "mechanism": "expected_input_contract",
                    "semantic_coherent": True,
                },
            }
        ],
        "pending_domain_workflow": {
            "workflow_name": "invoice_explanation",
            "execution_id": "exec-1",
            "resume_tool": "retomar_workflow",
            "owner_agent": "faturas_agent",
            "owner_intent": "billing_invoice_explanation",
            "pause": {
                "prompt": "Sanei sua dúvida?",
                "expected_input": {
                    "key": "resposta_usuario",
                    "allowed_values": ["SIM", "NAO"],
                    "normalize": "upper_strip",
                    "reprompt": "Não entendi. Essa explicação resolveu sua dúvida? Responda sim ou não.",
                    "unmatched": {
                        "meaningful_input": {"action": "resume_as", "value": "NAO"}
                    },
                },
            },
        },
    }
    decision = await router.route(state)
    assert decision.mcp_tools == ["retomar_workflow"]
    assert decision.metadata["workflow_resume"] is True
    assert decision.metadata["workflow_unmatched"] is True
    assert decision.metadata["workflow_unmatched_action"] == "resume_as"
    assert decision.metadata["normalized_input"] == "NAO"


@pytest.mark.asyncio
async def test_incoherent_unmatched_workflow_input_still_reprompts(tmp_path):
    router = _router(tmp_path)
    state = {
        "user_text": "ano",
        "sanitized_input": "ano",
        "route": "faturas_agent",
        "active_agent": "faturas_agent",
        "intent": "billing_invoice_explanation",
        "route_decision": {
            "route": "faturas_agent",
            "agent": "faturas_agent",
            "intent": "billing_invoice_explanation",
            "domain": "telecom",
        },
        "guardrail_decisions": [
            {
                "code": "COER",
                "allowed": True,
                "metadata": {
                    "mechanism": "expected_input_contract",
                    "semantic_coherent": False,
                },
            }
        ],
        "pending_domain_workflow": {
            "workflow_name": "invoice_explanation",
            "execution_id": "exec-1",
            "resume_tool": "retomar_workflow",
            "owner_agent": "faturas_agent",
            "owner_intent": "billing_invoice_explanation",
            "pause": {
                "prompt": "Sanei sua dúvida?",
                "expected_input": {
                    "key": "resposta_usuario",
                    "allowed_values": ["SIM", "NAO"],
                    "normalize": "upper_strip",
                    "reprompt": "Não entendi. Essa explicação resolveu sua dúvida? Responda sim ou não.",
                    "unmatched": {
                        "meaningful_input": {"action": "resume_as", "value": "NAO"}
                    },
                },
            },
        },
    }
    decision = await router.route(state)
    assert decision.mcp_tools == []
    assert decision.metadata["workflow_input_invalid"] is True
    assert decision.metadata["workflow_reprompt"].startswith("Não entendi.")


@pytest.mark.asyncio
async def test_runtime_uses_router_declared_resume_as_value_for_unmatched_input():
    runtime = _Runtime()
    state = {
        "sanitized_input": "pergunta substantiva",
        "user_text": "pergunta substantiva",
        "route": "faturas_agent",
        "active_agent": "faturas_agent",
        "intent": "billing_invoice_explanation",
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
                    "unmatched": {
                        "meaningful_input": {"action": "resume_as", "value": "NAO"}
                    },
                },
            },
        },
        "transaction_status": "WORKFLOW_PAUSED",
        "route_decision": {
            "route": "faturas_agent",
            "agent": "faturas_agent",
            "intent": "billing_invoice_explanation",
            "metadata": {
                "workflow_resume": True,
                "workflow_unmatched": True,
                "workflow_unmatched_action": "resume_as",
                "normalized_input": "NAO",
            },
        },
        "mcp_tools": ["retomar_workflow"],
    }
    results = await runtime.execute_tools_for_intent(state)
    assert len(results) == 1
    assert runtime.called[0] == "retomar_workflow"
    assert runtime.called[1]["resposta_usuario"] == "NAO"


def test_completed_workflow_final_response_preempts_prior_llm_composition():
    runtime = _Runtime()
    result = {
        "ok": True,
        "result": {
            "status": "COMPLETED",
            "workflow_name": "example",
            "output": {
                "formatar": {
                    "mensagem": "Pergunta antiga?",
                    "requires_llm_composition": True,
                    "await_user_input": True,
                },
                "finalizar": {
                    "success": True,
                    "workflow_response_final": True,
                    "mensagem": "Seu número de protocolo é 1234567890.",
                },
            },
            "state": {"current_node": "finalizar"},
        },
    }
    answer = runtime.build_direct_mcp_answer({}, [result], agent_label="Agent")
    assert answer == "Seu número de protocolo é 1234567890."


def test_completed_workflow_without_final_response_keeps_old_composition_behavior():
    runtime = _Runtime()
    result = {
        "ok": True,
        "result": {
            "status": "COMPLETED",
            "workflow_name": "example",
            "output": {
                "formatar": {
                    "mensagem": "Pergunta antiga?",
                    "requires_llm_composition": True,
                },
                "finalizar": {"success": True, "protocol_number": "123"},
            },
            "state": {"current_node": "finalizar"},
        },
    }
    assert runtime.build_direct_mcp_answer({}, [result], agent_label="Agent") is None

class _HandoffContinuityLLM:
    async def ainvoke(self, messages, **kwargs):
        if kwargs.get("profile_name") == "route_continuity":
            current = str(messages[-1].get("content") or "")
            if "atendente" in current.lower():
                return '{"decision":"HUMAN_HANDOFF","confidence":0.99,"reason":"pedido explícito de humano"}'
            return '{"decision":"CONTINUE","confidence":0.99,"reason":"continuidade"}'
        if kwargs.get("generation_name") == "workflow.expected_input.semantic_classifier":
            return "CONTINUAR"
        return '{}'


def _router_with_handoff_llm(tmp_path):
    routing = tmp_path / "routing-handoff.yaml"
    routing.write_text(ROUTING_YAML, encoding="utf-8")
    settings = SimpleNamespace(
        ROUTING_CONFIG_PATH=str(routing),
        ENABLE_LLM_ROUTER=False,
        ENABLE_ROUTE_STICKINESS=True,
        ROUTE_STICKINESS_LLM_PROFILE="route_continuity",
        ROUTE_STICKINESS_CONFIDENCE_THRESHOLD=0.7,
        ROUTE_STICKINESS_HISTORY_TURNS=2,
    )
    return EnterpriseRouter(settings, llm=_HandoffContinuityLLM())


@pytest.mark.asyncio
async def test_explicit_human_handoff_preempts_paused_expected_input_semantic_classifier(tmp_path):
    router = _router_with_handoff_llm(tmp_path)
    state = {
        "user_text": "quero falar com um atendente",
        "sanitized_input": "quero falar com um atendente",
        "route": "faturas_agent",
        "active_agent": "faturas_agent",
        "intent": "billing_invoice_explanation",
        "route_decision": {
            "route": "faturas_agent",
            "agent": "faturas_agent",
            "intent": "billing_invoice_explanation",
            "domain": "telecom",
        },
        "history": [
            {"role": "user", "content": "minha conta veio mais cara, quero entender"},
            {"role": "assistant", "content": "Com essa explicação, sanei sua dúvida?"},
        ],
        "transaction_status": "WORKFLOW_PAUSED",
        "pending_domain_workflow": {
            "workflow_name": "invoice_explanation",
            "execution_id": "exec-10",
            "resume_tool": "retomar_workflow",
            "owner_agent": "faturas_agent",
            "owner_intent": "billing_invoice_explanation",
            "pause": {
                "prompt": "Com essa explicação, sanei sua dúvida?",
                "expected_input": {
                    "key": "resposta_usuario",
                    "allowed_values": ["SIM", "NAO", "CONTINUAR"],
                    "normalize": "upper_strip",
                    "semantic_classifier": {
                        "enabled": True,
                        "include_relevant_context": True,
                        "prompt": "Classifique em {{ allowed_values }}: {{ user_input }}",
                        "option_actions": {"CONTINUAR": {"action": "contextual_reentry"}},
                    },
                },
            },
        },
    }

    decision = await router.route(state)

    assert decision.route == "human_handoff"
    assert decision.intent == "human_handoff"
    assert decision.handoff is True
    assert decision.metadata["session_control"] == "HUMAN_HANDOFF"
    assert decision.metadata["workflow_interruption"] == "human_handoff"
    assert decision.metadata["interrupted_workflow_name"] == "invoice_explanation"


@pytest.mark.asyncio
async def test_paused_expected_input_still_keeps_precedence_for_direct_match_with_global_probe_available(tmp_path):
    router = _router_with_handoff_llm(tmp_path)
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
            "execution_id": "exec-10",
            "resume_tool": "retomar_workflow",
            "owner_agent": "faturas_agent",
            "owner_intent": "billing_invoice_explanation",
            "pause": {
                "expected_input": {
                    "key": "resposta_usuario",
                    "allowed_values": ["SIM", "NAO", "CONTINUAR"],
                    "normalize": "upper_strip",
                }
            },
        },
    }

    decision = await router.route(state)

    assert decision.route == "faturas_agent"
    assert decision.metadata["workflow_resume"] is True
    assert decision.metadata["normalized_input"] == "SIM"


def test_completed_workflow_marks_next_turn_operational_boundary():
    runtime = _Runtime()
    state = {
        "route": "faturas_agent",
        "active_agent": "faturas_agent",
        "intent": "billing_invoice_explanation",
        "pending_domain_workflow": {
            "execution_id": "exec-1",
            "workflow_name": "invoice_explanation",
        },
        "transaction_status": "WORKFLOW_PAUSED",
    }
    completed = {
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
    }
    runtime._capture_pending_domain_workflow(state, completed)
    assert state["transaction_status"] == "COMPLETED"
    assert state["pending_domain_workflow"] is None
    assert state["operational_context_boundary_pending"] is True
    patch = runtime.transaction_state_patch(state)
    assert patch["operational_context_boundary_pending"] is True


@pytest.mark.asyncio
async def test_operational_context_reset_skips_route_continuity(tmp_path):
    router = _router(tmp_path)

    async def _must_not_run(*args, **kwargs):
        raise AssertionError("route continuity must not run after a closed workflow boundary")

    router.continuity.evaluate = _must_not_run
    state = {
        "user_text": "ah espera",
        "sanitized_input": "ah espera",
        "operational_context_reset": True,
        "route": "faturas_agent",
        "active_agent": "faturas_agent",
        "intent": "billing_invoice_explanation",
        "route_decision": {"route": "faturas_agent", "intent": "billing_invoice_explanation"},
        "context": {"session": {"metadata": {"workflow_state": "WAITING_BILLING_CONFIRMATION"}}},
        "history": [
            {"role": "user", "content": "quero saber por que minha conta subiu"},
            {"role": "assistant", "content": "Com essa explicação, sanei sua dúvida?"},
            {"role": "user", "content": "entendi, obrigado, era só isso"},
            {"role": "assistant", "content": "Seu número de protocolo é 1234567890."},
            {"role": "user", "content": "ah espera"},
        ],
    }
    decision = await router.route(state)
    assert decision.method in {"fallback", "keyword"}
    assert not (decision.metadata or {}).get("workflow_resume")
    assert decision.intent != "billing_invoice_explanation"


def test_workflow_response_final_overrides_stale_paused_status_and_sets_boundary():
    runtime = _Runtime()
    state = {
        "pending_domain_workflow": {
            "execution_id": "exec-final-stale",
            "workflow_name": "invoice_explanation",
        },
        "transaction_status": "WORKFLOW_PAUSED",
    }
    stale_adapter_result = {
        "ok": True,
        "result": {
            "result": {
                "status": "PAUSED",
                "execution_id": "exec-final-stale",
                "metadata": {
                    "workflow_name": "invoice_explanation",
                    "workflow_execution_id": "exec-final-stale",
                    "resume_tool": "retomar_workflow",
                },
                "output": {
                    "success": True,
                    "workflow_response_final": True,
                    "mensagem": "Seu número de protocolo é 1234567890.",
                },
                "state": {"current_node": "registrar_protocolo_aceite"},
                "pause": {
                    "expected_input": {
                        "allowed_values": ["SIM", "NAO", "CONTINUAR"]
                    }
                },
            }
        },
    }

    normalized = runtime._workflow_payload_from_tool_result(stale_adapter_result)
    assert normalized is not None
    assert normalized["status"] == "COMPLETED"
    assert normalized["metadata"]["status_normalized_from"] == "PAUSED"

    runtime._capture_pending_domain_workflow(state, stale_adapter_result)
    assert state["pending_domain_workflow"] is None
    assert state["transaction_status"] == "COMPLETED"
    assert state["operational_context_boundary_pending"] is True
