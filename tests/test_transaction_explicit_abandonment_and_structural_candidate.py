import json
from types import SimpleNamespace

import pytest

from agent_framework.routing.enterprise_router import EnterpriseRouter
from agent_framework.runtime.agent_runtime import AgentRuntimeMixin
from agent_framework.runtime.transaction_parameters import reconcile_transaction_parameters


class _RouterLLM:
    async def ainvoke(self, messages, **kwargs):
        prompt = messages[-1]["content"] if isinstance(messages[-1], dict) else str(messages[-1])
        low = prompt.lower()
        if kwargs.get("generation_name") == "llm.transaction_parameter_relevance":
            if "isso mesmo, pode cancelar" in low or "motivo é que desisti" in low or "motivo e que desisti" in low:
                return json.dumps({"relevance": "RELEVANT", "confidence": 0.99, "reason": "responde ao contexto solicitado"})
            return json.dumps({"relevance": "NOT_RELEVANT", "confidence": 0.99, "reason": "não responde ao parâmetro pendente"})
        if kwargs.get("profile_name") == "transaction_parameter_extraction" or "pending_parameters:" in prompt:
            return json.dumps({"subject": None, "valor": None})
        if (
            "nao quero cancelar. quero apenas verificar os meus servicos contratados" in prompt.lower()
            or "nao quero cancelar. quero apenas ver meus servicos contratados" in prompt.lower()
            or "nao quero mais cancelar. quero apenas ver os servicos que eu contratei" in prompt.lower()
        ):
            return json.dumps({
                "decision": "ABANDON",
                "intent": "product_services_information",
                "agent": "product_agent",
                "confidence": 0.99,
                "reason": "abandono explícito do cancelamento com novo objetivo",
            })
        if "nao quero mais cancelar" in prompt.lower() or "não quero mais cancelar" in prompt.lower():
            return json.dumps({
                "decision": "ABANDON",
                "intent": None,
                "agent": None,
                "confidence": 0.99,
                "reason": "abandono explícito sem novo objetivo",
            })
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
  - state: WAITING_CONTESTACAO_CONFIRMATION
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
  - name: product_services_information
    agent: product_agent
    priority: 40
    keywords: [servicos contratados, serviços contratados]
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
        "history": [
            {"role": "user", "content": "não reconheço o Tamboro Mensal, quero tirar da fatura"},
            {"role": "assistant", "content": "Qual é o valor da cobrança que você deseja contestar?"},
            {"role": "user", "content": message},
        ],
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
    assert decision.agent == "billing_agent"
    assert decision.metadata["transaction_interruption"] == "explicit_abandonment"


@pytest.mark.asyncio
async def test_explicit_abandonment_without_new_goal_does_not_rearm_tool(tmp_path):
    decision = await _router(tmp_path).route(_active_state("nao quero mais cancelar"))
    assert decision.intent == "state:TRANSACTION_ABANDONED"
    assert decision.agent == "contestacao_agent"
    assert decision.mcp_tools == []
    assert decision.metadata["transaction_interruption"] == "explicit_abandonment"
    assert decision.metadata["interrupted_intent"] == "contas_contestation"




def _awaiting_confirmation_state(message):
    return {
        "user_text": message,
        "sanitized_input": message,
        "next_state": "WAITING_CONTESTACAO_CONFIRMATION",
        "transaction_status": "AWAITING_CONFIRMATION",
        "intent": "state:WAITING_CONTESTACAO_CONFIRMATION",
        "active_agent": "contestacao_agent",
        "active_transaction": {
            "tool_name": "cancelar_vas_avulso",
            "arguments": {"subject": "Tamboro Mensal"},
            "status": "AWAITING_CONFIRMATION",
            "started_from_intent": "contas_vas_cancel",
        },
        "pending_tool_call": {
            "tool_name": "cancelar_vas_avulso",
            "arguments": {"subject": "Tamboro Mensal"},
        },
        "history": [
            {"role": "user", "content": "quero cancelar tamboro"},
            {"role": "assistant", "content": "Você confirma o cancelamento?"},
            {"role": "user", "content": message},
        ],
    }


@pytest.mark.asyncio
async def test_explicit_abandonment_precedes_awaiting_confirmation_and_routes_new_goal(tmp_path):
    decision = await _router(tmp_path).route(
        _awaiting_confirmation_state(
            "nao quero cancelar. quero apenas verificar os meus servicos contratados"
        )
    )
    assert decision.intent == "product_services_information"
    assert decision.agent == "product_agent"
    assert decision.metadata["transaction_interruption"] == "explicit_abandonment"
    assert decision.metadata["interrupted_intent"] == "contas_vas_cancel"
    assert not decision.metadata.get("transaction_turn_consumed")




@pytest.mark.asyncio
async def test_explicit_abandonment_precedes_generic_state_lock_without_transaction_status(tmp_path):
    state = _awaiting_confirmation_state(
        "nao quero cancelar. quero apenas ver meus servicos contratados"
    )
    # Reproduce the host/checkpoint shape observed in production: the domain
    # WAITING_* state is restored, but transaction_status is absent/stale.
    state.pop("transaction_status", None)
    decision = await _router(tmp_path).route(state)
    assert decision.intent == "product_services_information"
    assert decision.agent == "product_agent"
    assert decision.metadata["transaction_interruption"] == "explicit_abandonment"
    assert decision.metadata["interrupted_state"] == "WAITING_CONTESTACAO_CONFIRMATION"
    assert not decision.metadata.get("transaction_turn_consumed")


@pytest.mark.asyncio
async def test_explicit_abandonment_precedes_state_lock_with_only_domain_state_preserved(tmp_path):
    state = _awaiting_confirmation_state(
        "nao quero mais cancelar. quero apenas ver os servicos que eu contratei"
    )
    # Production checkpoint shape: only the domain WAITING_* lock survives.
    # No transaction_status, active_transaction or legacy pending tool latch.
    state.pop("transaction_status", None)
    state.pop("active_transaction", None)
    state.pop("pending_tool_call", None)
    state.pop("selected_tool_call", None)
    decision = await _router(tmp_path).route(state)
    assert decision.intent == "product_services_information"
    assert decision.agent == "product_agent"
    assert decision.metadata["transaction_interruption"] == "explicit_abandonment"
    assert decision.metadata["interrupted_state"] == "WAITING_CONTESTACAO_CONFIRMATION"
    assert not decision.metadata.get("transaction_turn_consumed")


@pytest.mark.asyncio
async def test_plain_negative_confirmation_remains_confirmation_not_abandon(tmp_path):
    decision = await _router(tmp_path).route(_awaiting_confirmation_state("não"))
    assert decision.intent == "state:WAITING_CONTESTACAO_CONFIRMATION"
    assert decision.agent == "contestacao_agent"
    assert decision.metadata["transaction_turn_consumed"] is True
    assert decision.metadata["transaction_confirmation_decision"] == "reject"
    assert "transaction_interruption" not in decision.metadata

class _MisleadingParameterRouterLLM(_RouterLLM):
    async def ainvoke(self, messages, **kwargs):
        prompt = messages[-1]["content"] if isinstance(messages[-1], dict) else str(messages[-1])
        generation = kwargs.get("generation_name")
        low = prompt.lower()
        # Relevance is a semantic gate before extraction. The extractor below is
        # intentionally misleading to prove that NOT_RELEVANT prevents a false
        # parameter value from stealing an abandonment turn.
        if generation == "llm.transaction_parameter_relevance":
            if "motivo é que desisti" in low or "motivo e que desisti" in low:
                return json.dumps({"relevance": "RELEVANT", "confidence": 0.99, "reason": "responde ao reason"})
            if "nao quero mais devolver" in low or "não quero mais devolver" in low or "nao quero mais cancelar" in low:
                return json.dumps({"relevance": "NOT_RELEVANT", "confidence": 0.99, "reason": "abandona a ação"})
            return json.dumps({"relevance": "NOT_RELEVANT", "confidence": 0.95, "reason": "não responde ao parâmetro"})
        if kwargs.get("profile_name") == "transaction_parameter_extraction" or "pending_parameters:" in prompt:
            if "motivo é que desisti" in low or "motivo e que desisti" in low:
                return json.dumps({"valor": "desisti"})
            if "nao quero mais cancelar" in low or "não quero mais cancelar" in low:
                return json.dumps({"valor": 14.99})
        if "nao quero mais devolver" in low or "não quero mais devolver" in low:
            return json.dumps({
                "decision": "ABANDON",
                "intent": "product_services_information",
                "agent": "product_agent",
                "confidence": 0.99,
                "reason": "abandono explícito da devolução com novo objetivo",
            })
        return await super().ainvoke(messages, **kwargs)


def _router_with_misleading_parameter_extractor(tmp_path):
    router = _router(tmp_path)
    router.llm = _MisleadingParameterRouterLLM()
    return router


@pytest.mark.asyncio
async def test_parameter_relevance_precedes_abandonment(tmp_path):
    state = _active_state("motivo é que desisti")
    state["missing_parameters"] = ["valor"]
    state["active_transaction"]["parameter_schema"] = {"valor": {"type": "string", "description": "motivo informado pelo cliente"}}
    decision = await _router_with_misleading_parameter_extractor(tmp_path).route(state)
    assert decision.intent == "state:COLLECTING_PARAMETERS"
    assert decision.metadata["transaction_turn_consumed"] is True
    assert decision.metadata["transaction_parameter_relevant"] is True
    assert decision.metadata["transaction_parameter_values"] == {"valor": "desisti"}
    assert "transaction_interruption" not in decision.metadata


@pytest.mark.asyncio
async def test_semantic_not_relevant_prevents_misleading_extractor_and_allows_abandon(tmp_path):
    decision = await _router_with_misleading_parameter_extractor(tmp_path).route(
        _active_state("nao quero mais cancelar")
    )
    assert decision.intent == "state:TRANSACTION_ABANDONED"
    assert decision.agent == "contestacao_agent"
    assert decision.mcp_tools == []
    assert decision.metadata["transaction_interruption"] == "explicit_abandonment"
    assert decision.metadata["transaction_parameter_relevant"] is False
    assert not decision.metadata.get("transaction_turn_consumed")


@pytest.mark.asyncio
async def test_abandon_plus_new_goal_after_parameter_relevance_fails(tmp_path):
    decision = await _router_with_misleading_parameter_extractor(tmp_path).route(
        _active_state("nao quero mais devolver. quero apenas ver os meus servicos contratados")
    )
    assert decision.intent == "product_services_information"
    assert decision.agent == "product_agent"
    assert decision.metadata["transaction_interruption"] == "explicit_abandonment"
    assert decision.metadata["transaction_parameter_relevant"] is False



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


class _AbandonRuntime(AgentRuntimeMixin):
    def __init__(self):
        self.tool_router = None
        self.llm = None


@pytest.mark.asyncio
async def test_runtime_abandon_cancels_only_active_transaction_without_rearming_tool():
    runtime = _AbandonRuntime()
    state = {
        "sanitized_input": "nao quero mais cancelar",
        "route_decision": {
            "intent": "state:TRANSACTION_ABANDONED",
            "agent": "orders_agent",
            "metadata": {"transaction_interruption": "explicit_abandonment"},
        },
        "transaction_status": "COLLECTING_PARAMETERS",
        "missing_parameters": ["order_id"],
        "active_transaction": {
            "tool_name": "cancelar_pedido",
            "arguments": {},
            "status": "COLLECTING_PARAMETERS",
            "started_from_intent": "retail_order_cancel",
        },
        "selected_tool_call": {"tool_name": "cancelar_pedido", "arguments": {}},
        "pending_topics": [{"operation_id": "op-x", "intent": "other_pending_intent"}],
    }

    results = await runtime.execute_tools_for_intent(state, tools=[])

    assert results == []
    assert state["transaction_status"] == "CANCELLED"
    assert state["active_transaction"] is None
    assert state["selected_tool_call"] == {}
    assert state["tool_policy_result"]["action"] == "cancelled_by_explicit_abandonment"
    # ABANDON encerra a ação ativa; não apaga outras ações pendentes por efeito colateral.
    assert state["pending_topics"] == [{"operation_id": "op-x", "intent": "other_pending_intent"}]

class _ReasonParameterRouterLLM(_RouterLLM):
    async def ainvoke(self, messages, **kwargs):
        prompt = messages[-1]["content"] if isinstance(messages[-1], dict) else str(messages[-1])
        lowered = prompt.lower()
        if kwargs.get("generation_name") == "llm.transaction_parameter_relevance":
            if "motivo é que desisti" in lowered or "motivo e que desisti" in lowered:
                return json.dumps({"relevance": "RELEVANT", "confidence": 0.99, "reason": "responde ao motivo"})
            if "nao quero mais devolver o pedido" in lowered or "não quero mais devolver o pedido" in lowered:
                return json.dumps({"relevance": "NOT_RELEVANT", "confidence": 0.99, "reason": "abandona a devolução"})
        if kwargs.get("profile_name") == "transaction_parameter_extraction" or "pending_parameters:" in prompt:
            if "motivo é que desisti" in lowered or "motivo e que desisti" in lowered:
                return json.dumps({"reason": "desisti"})
        if "nao quero mais devolver o pedido" in lowered or "não quero mais devolver o pedido" in lowered:
            return json.dumps({
                "decision": "ABANDON",
                "intent": None,
                "agent": None,
                "confidence": 0.99,
                "reason": "abandono explícito da devolução",
            })
        return await super().ainvoke(messages, **kwargs)


def _reason_collecting_state(message):
    return {
        "user_text": message,
        "sanitized_input": message,
        "next_state": "COLLECTING_ORDERS_PARAMETERS",
        "transaction_status": "COLLECTING_PARAMETERS",
        "missing_parameters": ["reason"],
        "intent": "state:COLLECTING_PARAMETERS",
        "active_agent": "orders_agent",
        "active_transaction": {
            "tool_name": "solicitar_devolucao",
            "arguments": {"order_id": "PED-1001"},
            "status": "COLLECTING_PARAMETERS",
            "started_from_intent": "retail_support_exchange_return",
            "parameter_schema": {"reason": {"type": "string", "description": "motivo da devolução"}},
            "tool_description": "Solicita devolução de pedido informando o motivo",
        },
        "history": [
            {"role": "user", "content": "quero devolver o pedido PED-1001"},
            {"role": "assistant", "content": "Qual o motivo da devolução?"},
            {"role": "user", "content": message},
        ],
    }


@pytest.mark.asyncio
async def test_parameter_value_desisti_is_not_abandon_when_reason_is_expected(tmp_path):
    router = _router(tmp_path)
    router.llm = _ReasonParameterRouterLLM()
    decision = await router.route(_reason_collecting_state("motivo é que desisti"))
    assert decision.intent == "state:COLLECTING_PARAMETERS"
    assert decision.agent == "contestacao_agent" or decision.agent == "orders_agent"
    assert decision.metadata["transaction_turn_consumed"] is True
    assert decision.metadata["transaction_parameter_values"] == {"reason": "desisti"}
    assert "transaction_interruption" not in decision.metadata


@pytest.mark.asyncio
async def test_action_scoped_abandon_still_preempts_reason_extraction(tmp_path):
    router = _router(tmp_path)
    router.llm = _ReasonParameterRouterLLM()
    # The action is explicitly abandoned; this must not be consumed as reason.
    decision = await router.route(_reason_collecting_state("nao quero mais devolver o pedido"))
    assert decision.metadata["transaction_interruption"] == "explicit_abandonment"


def test_abandonment_has_no_lexical_gate_in_router_source():
    from pathlib import Path
    source = Path("libs/agent_framework/src/agent_framework/routing/enterprise_router.py").read_text(encoding="utf-8")
    assert "_looks_like_explicit_abandonment" not in source
    assert "_looks_like_action_abandonment" not in source
    assert "cues = (" not in source
