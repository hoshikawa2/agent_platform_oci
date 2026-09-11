import json
from types import SimpleNamespace

import pytest

from agent_framework.routing.enterprise_router import EnterpriseRouter
from agent_framework.routing.models import IntentDefinition
from agent_framework.routing.multi_intent import MultiIntentPlanner


def _planner():
    return MultiIntentPlanner([
        IntentDefinition(name="cancel", agent="orders", priority=10, keywords=["cancelar pedido"], mcp_tools=["cancelar_pedido"]),
        IntentDefinition(name="invoice", agent="billing", priority=20, keywords=["segunda via"], mcp_tools=["consultar_fatura"]),
    ], {
        "enabled": True,
    }, transactional_tools={"cancelar_pedido"})


def test_builds_validated_plan_and_keeps_primary_first():
    plan = _planner().plan("quero cancelar pedido e preciso da segunda via")
    assert plan is not None
    assert [item.intent for item in plan.operations] == ["cancel", "invoice"]
    assert plan.operations[1].disposition == "execute"
    assert plan.operations[1].tools == ["consultar_fatura"]


def test_confirmation_with_secondary_does_not_lose_confirmation():
    plan = _planner().plan_confirmation_secondary(
        "sim e preciso da segunda via", primary_intent="cancel", primary_agent="orders"
    )
    assert plan is not None
    assert [item.intent for item in plan.operations] == ["cancel", "invoice"]
    assert MultiIntentPlanner.public_messages(plan) == []


def test_transactional_intent_is_primary_even_when_mentioned_second():
    plan = _planner().plan("preciso da segunda via e quero cancelar pedido")
    assert plan is not None
    assert [item.intent for item in plan.operations] == ["cancel", "invoice"]


def test_does_not_plan_single_intent_or_invent_unknown_intent():
    assert _planner().plan("quero cancelar pedido") is None
    assert _planner().plan("quero cancelar pedido e saber o clima") is None


def test_known_primary_with_actionable_unknown_creates_off_context_topic():
    plan = _planner().plan("quero cancelar pedido e alterar meu CNPJ")
    assert plan is not None
    assert plan.operations[1].intent == "off_context"
    assert plan.operations[1].disposition == "unsupported"


def test_confirmation_with_unknown_secondary_keeps_confirmation():
    plan = _planner().plan_confirmation_secondary(
        "sim e altere meu CNPJ", primary_intent="cancel", primary_agent="orders"
    )
    assert plan is not None
    assert plan.operations[0].intent == "cancel"
    assert plan.operations[1].intent == "off_context"


def test_single_word_keyword_does_not_match_a_longer_word_prefix():
    planner = MultiIntentPlanner([
        IntentDefinition(name="cancel", agent="orders", priority=10, keywords=["cancela"]),
        IntentDefinition(name="invoice", agent="billing", priority=20, keywords=["segunda via"]),
    ])
    plan = planner.plan("sim, pode cancelar e preciso da segunda via")
    assert plan is not None
    assert all(item.intent != "cancel" for item in plan.operations)
    assert [item.intent for item in plan.operations] == ["invoice", "off_context"]


def test_semantic_fallback_hydrates_ownership_from_configured_intents():
    plan = _planner().plan_from_semantic({
        "confidence": 0.92,
        "operations": [
            {"intent": "invoice", "source_text": "me encaminhe o boleto"},
            {"intent": "cancel", "source_text": "não quero mais o pedido"},
        ],
    })
    assert plan is not None
    assert [item.intent for item in plan.operations] == ["cancel", "invoice"]
    assert plan.operations[0].agent == "orders"
    assert plan.operations[0].tools == ["cancelar_pedido"]


def test_semantic_fallback_rejects_invented_intent_and_low_confidence():
    assert _planner().plan_from_semantic({
        "confidence": 0.99,
        "operations": [
            {"intent": "cancel", "source_text": "não quero mais o pedido"},
            {"intent": "invented", "source_text": "faça outra coisa"},
        ],
    }) is None
    assert _planner().plan_from_semantic({
        "confidence": 0.2,
        "operations": [
            {"intent": "cancel", "source_text": "não quero mais o pedido"},
            {"intent": "invoice", "source_text": "me encaminhe o boleto"},
        ],
    }) is None


def test_semantic_confirmation_preserves_primary_transaction():
    plan = _planner().plan_confirmation_from_semantic(
        {
            "confidence": 0.9,
            "operations": [
                {"intent": "invoice", "source_text": "também gostaria do boleto"},
            ],
        },
        primary_intent="cancel",
        primary_agent="orders",
    )
    assert plan is not None
    assert [item.intent for item in plan.operations] == ["cancel", "invoice"]


@pytest.mark.asyncio
async def test_router_uses_semantic_multi_intent_only_after_deterministic_miss(tmp_path):
    routing = tmp_path / "routing.yaml"
    routing.write_text("""
router:
  fallback_agent: billing
intents:
  - name: cancel
    agent: orders
    description: Encerrar uma encomenda existente
    keywords: [cancelar pedido]
    mcp_tools: [cancelar_pedido]
  - name: invoice
    agent: billing
    description: Obter documento de cobrança ou boleto
    keywords: [segunda via]
    mcp_tools: [consultar_fatura]
""", encoding="utf-8")
    policies = tmp_path / "tool_policies.yaml"
    policies.write_text("""
defaults:
  operation_type: read_only
tool_policies:
  cancelar_pedido:
    operation_type: transactional
    require_confirmation: true
""", encoding="utf-8")

    class SemanticMultiIntentLLM:
        calls = 0

        async def ainvoke(self, messages, **kwargs):
            self.calls += 1
            assert kwargs["generation_name"] == "llm.router.multi_intent"
            return json.dumps({
                "confidence": 0.94,
                "operations": [
                    {"intent": "cancel", "source_text": "encerrar minha encomenda"},
                    {"intent": "invoice", "source_text": "encaminhe o boleto"},
                ],
            })

    llm = SemanticMultiIntentLLM()
    router = EnterpriseRouter(SimpleNamespace(
        ROUTING_CONFIG_PATH=str(routing),
        TOOL_POLICIES_PATH=str(policies),
        ENABLE_LLM_ROUTER=True,
        ENABLE_ROUTE_STICKINESS=False,
    ), llm=llm)
    decision = await router.route({
        "user_text": "quero encerrar minha encomenda e encaminhe o boleto",
        "context": {},
    })

    assert llm.calls == 1
    assert decision.method == "llm"
    assert decision.intent == "cancel"
    assert decision.agent == "orders"
    assert decision.metadata["multi_intent_classifier"] == "llm"
    assert [
        item["intent"]
        for item in decision.metadata["multi_intent_plan"]["operations"]
    ] == ["cancel", "invoice"]
