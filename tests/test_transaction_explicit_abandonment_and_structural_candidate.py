import json
from types import SimpleNamespace

import pytest

from agent_framework.routing.enterprise_router import EnterpriseRouter
from agent_framework.runtime.agent_runtime import AgentRuntimeMixin
from agent_framework.runtime.transaction_parameters import reconcile_transaction_parameters


class _RouterLLM:
    async def ainvoke(self, messages, **kwargs):
        prompt = messages[-1]["content"] if isinstance(messages[-1], dict) else str(messages[-1])
        if kwargs.get("profile_name") == "transaction_parameter_extraction" or "pending_parameters:" in prompt:
            return json.dumps({"subject": None, "valor": None})
        if "esquece" in prompt.lower():
            return json.dumps({
                "decision": "ABANDON",
                "intent": "billing_invoice_explanation",
                "agent": "billing_agent",
                "confidence": 0.99,
                "reason": "abandono explícito da transação atual",
            })
        return json.dumps({
            "decision": "SHIFT",
            "intent": "contas_vas_cancel",
            "agent": "vas_agent",
            "confidence": 0.99,
            "reason": "classificação genérica motivada por cancelar",
        })


def _router(tmp_path):
    routing = tmp_path / "routing.yaml"
    routing.write_text(
        """
router:
  fallback_agent: contestacao_agent
  confidence_threshold: 0.70
state_policies:
  - state: COLLECTING_PARAMETERS
    agent: contestacao_agent
intents:
  - name: contas_contestation
    agent: contestacao_agent
    priority: 10
    keywords: [contestar]
  - name: contas_vas_cancel
    agent: vas_agent
    priority: 20
    keywords: [cancelar]
  - name: billing_invoice_explanation
    agent: billing_agent
    priority: 30
    keywords: [fatura]
""",
        encoding="utf-8",
    )
    return EnterpriseRouter(
        SimpleNamespace(
            ROUTING_CONFIG_PATH=str(routing),
            ENABLE_LLM_ROUTER=True,
            ENABLE_ROUTE_STICKINESS=False,
        ),
        llm=_RouterLLM(),
    )


def _active_state(message):
    return {
        "user_text": message,
        "sanitized_input": message,
        "next_state": "COLLECTING_PARAMETERS",
        "transaction_status": "COLLECTING_PARAMETERS",
        "missing_parameters": ["valor"],
        "intent": "state:COLLECTING_PARAMETERS",
        "active_agent": "contestacao_agent",
        "active_transaction": {
            "tool_name": "contestar_cobranca",
            "arguments": {"subject": "Tamboro Mensal"},
            "status": "COLLECTING_PARAMETERS",
            "started_from_intent": "contas_contestation",
            "parameter_schema": {"valor": {"type": "number"}},
        },
    }


@pytest.mark.asyncio
async def test_generic_shift_does_not_interrupt_active_transaction(tmp_path):
    decision = await _router(tmp_path).route(_active_state("isso mesmo, pode cancelar"))
    assert decision.intent == "state:COLLECTING_PARAMETERS"
    assert not (decision.metadata or {}).get("transaction_interruption")


@pytest.mark.asyncio
async def test_explicit_abandonment_can_leave_active_transaction(tmp_path):
    decision = await _router(tmp_path).route(_active_state("esquece isso, quero ver minha fatura"))
    assert decision.intent == "billing_invoice_explanation"
    assert decision.metadata["transaction_interruption"] == "explicit_abandonment"


class _PolicyRouter:
    def __init__(self):
        self.registry = SimpleNamespace(
            tools={"contestar_cobranca": object()},
            get_tool=lambda name: SimpleNamespace(
                selection_keywords=["contestar"],
                args_schema={
                    "subject": {"type": "string", "description": "item concreto da fatura"},
                    "valor": {"type": "number", "description": "valor associado"},
                },
                requires=["subject", "valor"],
                description="Contesta cobrança validada",
            ),
        )

    def resolve_execution_policy(self, tool_name, arguments=None):
        return {
            "operation_type": "transactional",
            "require_confirmation": True,
            "requires": ["subject", "valor"],
            "pre_validation": {"enabled": True, "tool": "validar_contestacao", "fail_open": False},
        }


class _UnresolvedReconcileLLM:
    async def ainvoke(self, messages, **kwargs):
        prompt = messages[-1]["content"]
        if kwargs.get("profile_name") == "transaction_parameter_extraction":
            if "FOCO PRINCIPAL DA RECONCILIAÇÃO" in prompt:
                return {"content": json.dumps({
                    "fields": {
                        "subject": {"decision": "unresolved", "value": None, "source": ""},
                        "valor": {"decision": "preserve", "value": 14.99, "source": "state"},
                    }
                })}
            return {"content": json.dumps({"subject": None, "valor": 14.99})}
        return {"content": "{}"}


class _CandidateRuntime(AgentRuntimeMixin):
    def __init__(self):
        self.tool_router = _PolicyRouter()
        self.llm = _UnresolvedReconcileLLM()
        self.calls = []

    async def _call_mcp_tool(self, tool_name, arguments, state):
        self.calls.append((tool_name, dict(arguments)))
        if tool_name == "validar_contestacao":
            subject = str(arguments.get("subject") or "")
            if "Tamboro Mensal" in subject and float(arguments.get("valor")) == 14.99:
                return {
                    "ok": True,
                    "tool_name": tool_name,
                    "result": {
                        "eligible": True,
                        "status": "ELIGIBLE",
                        "transaction_decision": {
                            "resolved_arguments": {"subject": "Tamboro Mensal", "valor": 14.99}
                        },
                    },
                }
        return {"ok": True, "tool_name": tool_name, "result": {"eligible": False, "status": "NEEDS_PARAMETER", "parameter": "subject"}}


@pytest.mark.asyncio
async def test_unique_anchored_block_is_candidate_only_and_prevalidator_canonicalizes():
    runtime = _CandidateRuntime()
    state = {
        "user_text": "é a de quatorze e noventa e nove",
        "sanitized_input": "é a de quatorze e noventa e nove",
        "mcp_tools": ["contestar_cobranca"],
        "route": "contestacao_agent",
        "active_agent": "contestacao_agent",
        "intent": "contas_contestation",
        "route_decision": {"metadata": {}},
        "transaction_status": "COLLECTING_PARAMETERS",
        "missing_parameters": ["subject"],
        "active_transaction": {
            "tool_name": "contestar_cobranca",
            "arguments": {"valor": 14.99},
            "status": "COLLECTING_PARAMETERS",
            "requires": ["subject", "valor"],
            "parameter_schema": {
                "subject": {"type": "string", "description": "item concreto da fatura"},
                "valor": {"type": "number", "description": "valor associado"},
            },
            "parameter_conversational_context": (
                "history:1: assistant: Houve: * Cobrança Tamboro Mensal no valor de R$ 14,99 no dia 01/11/25. "
                "* Cobrança TIM Fashion Mensal no valor de R$ 10,00 no dia 01/11/25."
            ),
        },
        "selected_tool_call": {"tool_name": "contestar_cobranca", "arguments": {"valor": 14.99}},
    }

    result = await runtime.execute_tools_for_intent(state, tools=[])

    assert state["transaction_status"] == "AWAITING_CONFIRMATION"
    assert state["pending_tool_call"]["arguments"]["subject"] == "Tamboro Mensal"
    assert state["pending_tool_call"]["arguments"]["valor"] == 14.99
    assert state["transaction_parameter_reconciliation"]["applied_structural_candidates"] == {
        "subject": "unique_anchored_evidence_block"
    }
    validator_args = runtime.calls[0][1]
    assert validator_args["subject"].startswith("Cobrança Tamboro Mensal")
    assert result[-1]["awaiting_confirmation"] is True

@pytest.mark.asyncio
async def test_current_turn_value_then_unique_anchor_reaches_confirmation_from_empty_transaction():
    """Regression for Contas scenario 08: current amount first, temporal subject second."""
    runtime = _CandidateRuntime()
    state = {
        "user_text": "é a de quatorze e noventa e nove",
        "sanitized_input": "é a de quatorze e noventa e nove",
        "mcp_tools": ["contestar_cobranca"],
        "route": "contestacao_agent",
        "active_agent": "contestacao_agent",
        "intent": "contas_contestation",
        "route_decision": {"metadata": {}},
        "transaction_status": "COLLECTING_PARAMETERS",
        "missing_parameters": ["subject", "valor"],
        "active_transaction": {
            "tool_name": "contestar_cobranca",
            "arguments": {},
            "status": "COLLECTING_PARAMETERS",
            "requires": ["subject", "valor"],
            "parameter_schema": {
                "subject": {"type": "string", "description": "item concreto da fatura"},
                "valor": {"type": "number", "description": "valor monetário associado"},
            },
            "parameter_conversational_context": (
                "history:1: assistant: Houve: * Cobrança Tamboro Mensal no valor de R$ 14,99 no dia 01/11/25. "
                "* Cobrança TIM Fashion Mensal no valor de R$ 10,00 no dia 01/11/25."
            ),
        },
        "selected_tool_call": {"tool_name": "contestar_cobranca", "arguments": {}},
    }

    result = await runtime.execute_tools_for_intent(state, tools=[])

    assert state["transaction_parameter_collection"]["resolved_fields"] == ["valor"]
    assert state["transaction_status"] == "AWAITING_CONFIRMATION"
    assert state["pending_tool_call"]["arguments"]["subject"] == "Tamboro Mensal"
    assert state["pending_tool_call"]["arguments"]["valor"] == 14.99
    assert result[-1]["awaiting_confirmation"] is True


class _ClearMissingSubjectReconcileLLM(_UnresolvedReconcileLLM):
    async def ainvoke(self, messages, **kwargs):
        prompt = messages[-1]["content"]
        if kwargs.get("profile_name") == "transaction_parameter_extraction":
            if "FOCO PRINCIPAL DA RECONCILIAÇÃO" in prompt:
                return {"content": json.dumps({
                    "fields": {
                        "subject": {"decision": "clear", "value": None, "source": "history:1"},
                        "valor": {"decision": "preserve", "value": 14.99, "source": "state"},
                    }
                })}
            return {"content": json.dumps({"subject": None, "valor": 14.99})}
        return {"content": "{}"}


@pytest.mark.asyncio
async def test_initially_missing_subject_clear_still_allows_unique_anchored_candidate():
    """Scenario 08: clear on an already-missing field must not suppress candidate fallback."""
    rec = await reconcile_transaction_parameters(
        _ClearMissingSubjectReconcileLLM(),
        text="é a de quatorze e noventa e nove",
        tool_name="contestar_cobranca",
        parameter_names=["subject", "valor"],
        known_arguments={"valor": 14.99},
        parameter_schema={
            "subject": {"type": "string", "description": "item concreto da fatura"},
            "valor": {"type": "number", "description": "valor monetário associado"},
        },
        tool_description="Contesta uma cobrança identificada por item e valor",
        conversational_context=(
            "priority_3_previous_assistant_tool_or_evidence_context:\n"
            "history:1: assistant: Analisando a sua fatura atual. * Cobrança Tamboro Mensal no valor de R$ 14,99 no dia 01/11/25. "
            "* Cobrança TIM Fashion Mensal no valor de R$ 10,00 no dia 01/11/25.\n"
            "priority_4_previous_user_utterances:\n"
            "history:2: user: tem uma cobrança aqui que eu não reconheço"
        ),
    )

    assert rec["decisions"]["subject"] == "clear"
    assert rec["clear_fields"] == ["subject"]
    assert rec["candidates"] == {
        "subject": "Cobrança Tamboro Mensal no valor de R$ 14,99 no dia 01/11/25."
    }
    assert rec["candidate_provenance"] == {
        "subject": "unique_anchored_evidence_block"
    }
