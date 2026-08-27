from types import SimpleNamespace

import pytest

from agent_framework.routing.enterprise_router import EnterpriseRouter


class _LLM:
    async def ainvoke(self, messages, **kwargs):
        return '{"decision":"SHIFT","intent":"contas_vas_information","agent":"vas_agent","confidence":0.96,"reason":"nova consulta de serviços"}'


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
            return '{"decision":"SHIFT","intent":"contas_vas_information","agent":"vas_agent","confidence":0.30,"reason":"incerto"}'

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

@pytest.mark.asyncio
async def test_active_transaction_without_next_state_still_allows_intent_shift(tmp_path):
    routing = tmp_path / "routing.yaml"
    routing.write_text(
        """
router:
  fallback_agent: billing_agent
  confidence_threshold: 0.70
state_policies:
  - state: COLLECTING_ORDER_PARAMETERS
    agent: orders_agent
intents:
  - name: billing_invoice_explanation
    domain: telecom
    agent: billing_agent
    priority: 10
    keywords: [vencimento]
  - name: retail_order_cancel
    domain: retail
    agent: orders_agent
    priority: 20
    keywords: [cancelar pedido]
""",
        encoding="utf-8",
    )
    settings = SimpleNamespace(
        ROUTING_CONFIG_PATH=str(routing),
        ENABLE_LLM_ROUTER=False,
        ENABLE_ROUTE_STICKINESS=False,
    )
    router = EnterpriseRouter(settings)
    state = {
        "user_text": "esquece, quero a data de vencimento de minha fatura",
        "sanitized_input": "esquece, quero a data de vencimento de minha fatura",
        # Reproduz o template: latch transacional persistido, mas next_state ausente.
        "next_state": None,
        "transaction_status": "COLLECTING_PARAMETERS",
        "missing_parameters": ["order_id"],
        "selected_tool_call": {"tool_name": "cancelar_pedido", "arguments": {}},
        "active_agent": "orders_agent",
        "route_decision": {
            "route": "orders_agent",
            "agent": "orders_agent",
            "intent": "retail_order_cancel",
            "confidence": 0.95,
            "method": "keyword",
        },
    }

    decision = await router.route(state)

    assert decision.intent == "billing_invoice_explanation"
    assert decision.agent == "billing_agent"
    assert decision.metadata["transaction_interruption"] == "intent_shift"
    assert decision.metadata["transaction_state_recovered"] is True


@pytest.mark.asyncio
async def test_missing_next_state_does_not_treat_order_id_as_intent_shift(tmp_path):
    routing = tmp_path / "routing.yaml"
    routing.write_text(
        """
router:
  fallback_agent: billing_agent
  confidence_threshold: 0.70
state_policies:
  - state: COLLECTING_ORDER_PARAMETERS
    agent: orders_agent
intents:
  - name: billing_invoice_explanation
    agent: billing_agent
    priority: 10
    keywords: [fatura, vencimento]
  - name: retail_order_cancel
    agent: orders_agent
    priority: 20
    keywords: [cancelar pedido]
""",
        encoding="utf-8",
    )
    settings = SimpleNamespace(
        ROUTING_CONFIG_PATH=str(routing),
        ENABLE_LLM_ROUTER=False,
        ENABLE_ROUTE_STICKINESS=False,
    )
    router = EnterpriseRouter(settings)
    state = {
        "user_text": "PED-1001",
        "sanitized_input": "PED-1001",
        "next_state": None,
        "transaction_status": "COLLECTING_PARAMETERS",
        "missing_parameters": ["order_id"],
        "selected_tool_call": {"tool_name": "cancelar_pedido", "arguments": {}},
        "active_agent": "orders_agent",
        "route_decision": {
            "route": "orders_agent",
            "agent": "orders_agent",
            "intent": "retail_order_cancel",
        },
    }

    decision = await router.route(state)
    assert (decision.metadata or {}).get("transaction_interruption") is None

@pytest.mark.asyncio
async def test_missing_next_state_parameter_answer_recovers_transaction_state_before_continuity(tmp_path):
    """Regressão: parâmetro de uma transação ativa não pode cair no route-continuity.

    Reproduz o caso Contas de forma genérica: o latch transacional sobreviveu ao
    checkpoint, ``next_state`` não, e o usuário fornece exatamente o parâmetro
    faltante. A decisão deve continuar determinística (method=state), preservando
    a tool ativa para o AgentRuntime completar os argumentos já coletados.
    """
    routing = tmp_path / "routing.yaml"
    routing.write_text(
        """
router:
  fallback_agent: contestacao_agent
  confidence_threshold: 0.70
state_policies: []
intents:
  - name: contas_contestation
    agent: contestacao_agent
    priority: 20
    keywords: [nao contratei]
""",
        encoding="utf-8",
    )
    settings = SimpleNamespace(
        ROUTING_CONFIG_PATH=str(routing),
        ENABLE_LLM_ROUTER=False,
        ENABLE_ROUTE_STICKINESS=True,
    )
    router = EnterpriseRouter(settings)
    state = {
        "user_text": "R$ 71,99",
        "sanitized_input": "R$ 71,99",
        "next_state": None,
        "transaction_status": "COLLECTING_PARAMETERS",
        "missing_parameters": ["valor"],
        "selected_tool_call": {
            "tool_name": "contestar_cobranca",
            "arguments": {"subject": "Plano Exemplo"},
        },
        "active_agent": "contestacao_agent",
        "route": "contestacao_agent",
        "route_decision": {
            "route": "contestacao_agent",
            "agent": "contestacao_agent",
            "intent": "contas_contestation",
        },
    }

    decision = await router.route(state)

    assert decision.method == "state"
    assert decision.agent == "contestacao_agent"
    assert decision.intent == "state:COLLECTING_PARAMETERS"
    assert decision.next_state == "COLLECTING_PARAMETERS"
    assert decision.metadata["transaction_state_recovered"] is True


def test_agent_state_declares_durable_transaction_latch():
    """O schema do host deve manter os campos que o AgentRuntime persiste."""
    import importlib.util
    from pathlib import Path

    state_path = Path(__file__).parents[1] / "templates" / "agent_template_backend" / "app" / "state.py"
    spec = importlib.util.spec_from_file_location("contas_agent_state_v10", state_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    annotations = module.AgentState.__annotations__
    assert "active_transaction" in annotations
    assert "last_transaction" in annotations
