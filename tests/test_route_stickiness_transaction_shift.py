from types import SimpleNamespace

from agent_framework.routing.enterprise_router import EnterpriseRouter
from agent_framework.routing.models import RouteDecision


def test_explicit_keyword_shift_preempts_stickiness():
    d = RouteDecision(route="support_agent", agent="support_agent", intent="retail_support_exchange_return", method="keyword", metadata={"matched_keyword": "devolver pedido"})
    assert EnterpriseRouter._is_explicit_intent_shift(d) is True


def test_short_generic_keyword_does_not_preempt():
    d = RouteDecision(route="x", agent="x", intent="x", method="keyword", metadata={"matched_keyword": "id"})
    assert EnterpriseRouter._is_explicit_intent_shift(d) is False
