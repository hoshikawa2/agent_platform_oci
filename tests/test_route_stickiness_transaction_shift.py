import pytest
from types import SimpleNamespace

from agent_framework.routing.enterprise_router import EnterpriseRouter
from agent_framework.routing.models import RouteDecision


def test_explicit_keyword_shift_preempts_stickiness():
    d = RouteDecision(route="support_agent", agent="support_agent", intent="retail_support_exchange_return", method="keyword", metadata={"matched_keyword": "devolver pedido"})
    assert EnterpriseRouter._is_explicit_intent_shift(d) is True


def test_short_generic_keyword_does_not_preempt():
    d = RouteDecision(route="x", agent="x", intent="x", method="keyword", metadata={"matched_keyword": "id"})
    assert EnterpriseRouter._is_explicit_intent_shift(d) is False


def test_same_agent_explicit_intent_shift_must_preempt_stickiness():
    router = object.__new__(EnterpriseRouter)
    router.intents = []
    # This test documents the key regression: changing from a read-only intent
    # to a transactional intent handled by the SAME agent must still be treated
    # as an explicit intent shift. The route() integration tests exercise the
    # full async path; here we lock the explicitness predicate itself.
    d = RouteDecision(
        route="orders_agent",
        agent="orders_agent",
        intent="retail_order_cancel",
        method="keyword",
        metadata={"matched_keyword": "cancelar pedido"},
    )
    assert EnterpriseRouter._is_explicit_intent_shift(d) is True

@pytest.mark.asyncio
async def test_same_agent_transaction_keyword_preempts_continuity(monkeypatch):
    """Regression: tracking -> cancelar pedido must not reuse tracking intent."""
    from agent_framework.routing.models import IntentDefinition

    class _Continuity:
        async def evaluate(self, state, *, intents):
            raise AssertionError("continuity must be preempted by explicit intent shift")

    router = object.__new__(EnterpriseRouter)
    router.state_policies = []
    router.intents = [
        IntentDefinition(
            name="retail_order_cancel",
            domain="retail",
            agent="orders_agent",
            description="cancelamento",
            priority=20,
            mcp_tools=["consultar_pedido", "cancelar_pedido"],
            keywords=["cancelar pedido"],
            examples=[],
            enabled=True,
        ),
        IntentDefinition(
            name="retail_order_tracking",
            domain="retail",
            agent="orders_agent",
            description="tracking",
            priority=30,
            mcp_tools=["consultar_pedido", "consultar_entrega"],
            keywords=["pedido"],
            examples=[],
            enabled=True,
        ),
    ]
    router.continuity = _Continuity()
    router.enable_llm_router = False
    router.llm = None
    router.telemetry = None
    router.fallback_agent = "billing_agent"

    decision = await router.route({
        "user_text": "quero cancelar pedido",
        "sanitized_input": "quero cancelar pedido",
        "active_agent": "orders_agent",
        "intent": "retail_order_tracking",
        "route_decision": {
            "route": "orders_agent",
            "agent": "orders_agent",
            "intent": "retail_order_tracking",
            "domain": "retail",
            "mcp_tools": ["consultar_pedido", "consultar_entrega"],
        },
        "context": {"session": {}},
    })

    assert decision.agent == "orders_agent"
    assert decision.intent == "retail_order_cancel"
    assert decision.method == "keyword"
    assert decision.mcp_tools == ["consultar_pedido", "cancelar_pedido"]
    assert decision.metadata["route_stickiness_preempted"] is True
    assert decision.metadata["previous_agent"] == "orders_agent"
    assert decision.metadata["previous_intent"] == "retail_order_tracking"


@pytest.mark.parametrize(
    "message",
    [
        "quero cancelar meu pedido",
        "quero cancelar o meu pedido",
        "pode cancelar esse pedido",
        "gostaria de cancelar meu pedido",
    ],
)
@pytest.mark.asyncio
async def test_same_agent_transaction_shift_with_inserted_words_is_deterministic(message):
    """Inserted connector/pronoun words must not force an LLM continuity call."""
    from agent_framework.routing.models import IntentDefinition

    class _Continuity:
        async def evaluate(self, state, *, intents):
            raise AssertionError("continuity LLM must not run for explicit deterministic transaction shift")

    router = object.__new__(EnterpriseRouter)
    router.state_policies = []
    router.intents = [
        IntentDefinition(
            name="retail_order_cancel", domain="retail", agent="orders_agent",
            description="cancelamento", priority=20,
            mcp_tools=["consultar_pedido", "cancelar_pedido"],
            keywords=["cancelar pedido"], examples=[], enabled=True,
        ),
        IntentDefinition(
            name="retail_order_tracking", domain="retail", agent="orders_agent",
            description="tracking", priority=30,
            mcp_tools=["consultar_pedido", "consultar_entrega"],
            keywords=["pedido"], examples=[], enabled=True,
        ),
    ]
    router.continuity = _Continuity()
    router.enable_llm_router = False
    router.llm = None
    router.telemetry = None
    router.fallback_agent = "billing_agent"

    decision = await router.route({
        "user_text": message, "sanitized_input": message,
        "active_agent": "orders_agent", "intent": "retail_order_tracking",
        "route_decision": {
            "route": "orders_agent", "agent": "orders_agent",
            "intent": "retail_order_tracking", "domain": "retail",
            "mcp_tools": ["consultar_pedido", "consultar_entrega"],
        },
        "context": {"session": {}},
    })

    assert decision.intent == "retail_order_cancel"
    assert decision.agent == "orders_agent"
    assert decision.mcp_tools == ["consultar_pedido", "cancelar_pedido"]
    assert decision.metadata["route_stickiness_preempted"] is True
    assert decision.metadata["keyword_match_strategy"] == "ordered_tokens"


def test_ordered_keyword_match_is_conservative():
    assert EnterpriseRouter._ordered_keyword_match("cancelar pedido", "quero cancelar meu pedido") is True
    assert EnterpriseRouter._ordered_keyword_match("cancelar pedido", "quero pedido e talvez cancelar depois") is False
    assert EnterpriseRouter._ordered_keyword_match("pedido", "meu pedido") is False


def test_ordered_content_keyword_match_tolerates_omitted_short_connectors():
    assert EnterpriseRouter._ordered_content_keyword_match(
        "qual é o meu plano", "qual o meu plano"
    ) is True
    assert EnterpriseRouter._ordered_content_keyword_match(
        "qual é o meu plano", "quero ver minha fatura"
    ) is False


@pytest.mark.asyncio
async def test_loaded_domain_style_plan_shift_preempts_continuity_without_llm():
    """Regression: invoice -> plan must work from configured keywords, even same agent.

    This mirrors applications such as Contas where two intents may be handled by
    the same agent but require different MCP tools. The routing core must not
    know application-specific intent or agent names.
    """
    from agent_framework.routing.models import IntentDefinition

    class _Continuity:
        async def evaluate(self, state, *, intents):
            raise AssertionError("continuity LLM must not run for explicit configured intent shift")

    router = object.__new__(EnterpriseRouter)
    router.state_policies = []
    router.intents = [
        IntentDefinition(
            name="domain_plan_information",
            domain="customer_domain",
            agent="customer_agent",
            description="informações de plano",
            priority=142,
            mcp_tools=["consultar_plano"],
            keywords=["qual é o meu plano", "plano contratado"],
            examples=[],
            enabled=True,
        ),
        IntentDefinition(
            name="domain_invoice_query",
            domain="customer_domain",
            agent="customer_agent",
            description="consulta de fatura",
            priority=140,
            mcp_tools=["consultar_faturas"],
            keywords=["quero minha fatura", "fatura atual"],
            examples=[],
            enabled=True,
        ),
    ]
    router.continuity = _Continuity()
    router.enable_llm_router = False
    router.llm = None
    router.telemetry = None
    router.fallback_agent = "customer_agent"

    message = "qual o meu plano"
    decision = await router.route({
        "user_text": message,
        "sanitized_input": message,
        "active_agent": "customer_agent",
        "intent": "domain_invoice_query",
        "route_decision": {
            "route": "customer_agent",
            "agent": "customer_agent",
            "intent": "domain_invoice_query",
            "domain": "customer_domain",
            "mcp_tools": ["consultar_faturas"],
        },
        "context": {"session": {}},
    })

    assert decision.intent == "domain_plan_information"
    assert decision.agent == "customer_agent"
    assert decision.mcp_tools == ["consultar_plano"]
    assert decision.method == "keyword"
    assert decision.metadata["route_stickiness_preempted"] is True
    assert decision.metadata["previous_intent"] == "domain_invoice_query"
    assert decision.metadata["keyword_match_strategy"] == "ordered_content_tokens"
