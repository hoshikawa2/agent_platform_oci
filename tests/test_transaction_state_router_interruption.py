from types import SimpleNamespace

import pytest

from agent_framework.routing.enterprise_router import EnterpriseRouter


class _LLM:
    async def ainvoke(self, messages, **kwargs):
        return '{"intent":"contas_vas_information","agent":"vas_agent","confidence":0.96,"reason":"nova consulta de serviços"}'


@pytest.mark.asyncio
async def test_state_policy_allows_high_confidence_new_intent(tmp_path):
    routing = tmp_path / "routing.yaml"
    routing.write_text(
        """
router:
  fallback_agent: faturas_agent
  confidence_threshold: 0.70
state_policies:
  - state: COLLECTING_CONTESTACAO_PARAMETERS
    agent: contestacao_agent
intents:
  - name: contas_contestation
    agent: contestacao_agent
    priority: 10
    keywords: [contestar]
  - name: contas_vas_information
    agent: vas_agent
    priority: 20
    keywords: [serviços ativos]
""",
        encoding="utf-8",
    )
    settings = SimpleNamespace(
        ROUTING_CONFIG_PATH=str(routing),
        ENABLE_LLM_ROUTER=True,
        ENABLE_ROUTE_STICKINESS=False,
    )
    router = EnterpriseRouter(settings, llm=_LLM())
    state = {
        "user_text": "quais são meus serviços?",
        "sanitized_input": "quais são meus serviços?",
        "next_state": "COLLECTING_CONTESTACAO_PARAMETERS",
        "intent": "state:COLLECTING_CONTESTACAO_PARAMETERS",
        "active_agent": "contestacao_agent",
        "active_transaction": {
            "tool_name": "contestar_cobranca",
            "status": "COLLECTING_PARAMETERS",
            "started_from_intent": "contas_contestation",
        },
    }

    decision = await router.route(state)

    assert decision.intent == "contas_vas_information"
    assert decision.agent == "vas_agent"
    assert decision.metadata["transaction_interruption"] == "intent_shift"
    assert decision.next_state is None


@pytest.mark.asyncio
async def test_state_policy_keeps_short_parameter_answer_in_transaction(tmp_path):
    routing = tmp_path / "routing.yaml"
    routing.write_text(
        """
router:
  fallback_agent: faturas_agent
  confidence_threshold: 0.70
state_policies:
  - state: COLLECTING_CONTESTACAO_PARAMETERS
    agent: contestacao_agent
intents:
  - name: contas_contestation
    agent: contestacao_agent
    priority: 10
    keywords: [contestar]
  - name: contas_vas_information
    agent: vas_agent
    priority: 20
    keywords: [serviços ativos]
""",
        encoding="utf-8",
    )

    class _LowConfidenceLLM:
        async def ainvoke(self, messages, **kwargs):
            return '{"intent":"contas_vas_information","agent":"vas_agent","confidence":0.30,"reason":"incerto"}'

    settings = SimpleNamespace(
        ROUTING_CONFIG_PATH=str(routing),
        ENABLE_LLM_ROUTER=True,
        ENABLE_ROUTE_STICKINESS=False,
    )
    router = EnterpriseRouter(settings, llm=_LowConfidenceLLM())
    state = {
        "user_text": "TIM Music",
        "sanitized_input": "TIM Music",
        "next_state": "COLLECTING_CONTESTACAO_PARAMETERS",
        "intent": "state:COLLECTING_CONTESTACAO_PARAMETERS",
        "active_agent": "contestacao_agent",
        "active_transaction": {
            "tool_name": "contestar_cobranca",
            "status": "COLLECTING_PARAMETERS",
            "started_from_intent": "contas_contestation",
        },
    }

    decision = await router.route(state)

    assert decision.method == "state"
    assert decision.agent == "contestacao_agent"
    assert decision.intent == "state:COLLECTING_CONTESTACAO_PARAMETERS"

@pytest.mark.asyncio
async def test_state_policy_keeps_currency_value_as_pending_parameter_even_if_llm_wants_new_intent(tmp_path):
    routing = tmp_path / "routing.yaml"
    routing.write_text(
        """
router:
  fallback_agent: faturas_agent
  confidence_threshold: 0.70
state_policies:
  - state: COLLECTING_CONTESTACAO_PARAMETERS
    agent: contestacao_agent
intents:
  - name: contas_contestation
    agent: contestacao_agent
    priority: 10
    keywords: [contestar]
  - name: contas_invoice_explanation
    agent: faturas_agent
    priority: 20
    keywords: [fatura]
""",
        encoding="utf-8",
    )

    class _InvoiceLLM:
        async def ainvoke(self, messages, **kwargs):
            return '{"intent":"contas_invoice_explanation","agent":"faturas_agent","confidence":0.95,"reason":"valor isolado"}'

    settings = SimpleNamespace(
        ROUTING_CONFIG_PATH=str(routing),
        ENABLE_LLM_ROUTER=True,
        ENABLE_ROUTE_STICKINESS=False,
    )
    router = EnterpriseRouter(settings, llm=_InvoiceLLM())
    state = {
        "user_text": "R$ 71,99",
        "sanitized_input": "R$ 71,99",
        "next_state": "COLLECTING_CONTESTACAO_PARAMETERS",
        "intent": "state:COLLECTING_CONTESTACAO_PARAMETERS",
        "active_agent": "contestacao_agent",
        "missing_parameters": ["valor"],
        "active_transaction": {
            "tool_name": "contestar_cobranca",
            "status": "COLLECTING_PARAMETERS",
            "started_from_intent": "contas_contestation",
            "arguments": {"subject": "TIM CTRL Redes Sociais 8.0"},
        },
    }

    decision = await router.route(state)

    assert decision.method == "state"
    assert decision.agent == "contestacao_agent"
    assert decision.intent == "state:COLLECTING_CONTESTACAO_PARAMETERS"
    assert "transaction_interruption" not in (decision.metadata or {})


@pytest.mark.asyncio
async def test_state_policy_still_allows_clear_question_to_interrupt_pending_value(tmp_path):
    routing = tmp_path / "routing.yaml"
    routing.write_text(
        """
router:
  fallback_agent: faturas_agent
  confidence_threshold: 0.70
state_policies:
  - state: COLLECTING_CONTESTACAO_PARAMETERS
    agent: contestacao_agent
intents:
  - name: contas_contestation
    agent: contestacao_agent
    priority: 10
    keywords: [contestar]
  - name: contas_vas_information
    agent: vas_agent
    priority: 20
    keywords: [serviços]
""",
        encoding="utf-8",
    )
    settings = SimpleNamespace(
        ROUTING_CONFIG_PATH=str(routing),
        ENABLE_LLM_ROUTER=True,
        ENABLE_ROUTE_STICKINESS=False,
    )
    router = EnterpriseRouter(settings, llm=_LLM())
    state = {
        "user_text": "quais são meus serviços?",
        "sanitized_input": "quais são meus serviços?",
        "next_state": "COLLECTING_CONTESTACAO_PARAMETERS",
        "intent": "state:COLLECTING_CONTESTACAO_PARAMETERS",
        "active_agent": "contestacao_agent",
        "missing_parameters": ["valor"],
        "active_transaction": {
            "tool_name": "contestar_cobranca",
            "status": "COLLECTING_PARAMETERS",
            "started_from_intent": "contas_contestation",
        },
    }

    decision = await router.route(state)
    assert decision.intent == "contas_vas_information"
    assert decision.metadata["transaction_interruption"] == "intent_shift"
