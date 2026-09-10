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
