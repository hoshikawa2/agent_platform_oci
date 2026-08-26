from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agent_framework.routing.enterprise_router import EnterpriseRouter
from agent_framework.runtime.agent_runtime import AgentRuntimeMixin


class _SemanticLLM:
    """Test double: parameter extraction + intent-shift classification."""

    async def ainvoke(self, messages, **kwargs):
        prompt = messages[-1]["content"] if isinstance(messages[-1], dict) else str(messages[-1])
        profile = kwargs.get("profile_name")
        if profile == "transaction_parameter_extraction" or "pending_parameters:" in prompt:
            marker = "user_message: "
            user = prompt.split(marker, 1)[1].split("\nFormato obrigatório:", 1)[0].strip() if marker in prompt else ""
            pending_raw = prompt.split("pending_parameters: ", 1)[1].split("\n", 1)[0]
            pending = json.loads(pending_raw)
            values = {name: None for name in pending}
            low = user.lower()
            if "ped-1001" in low and "order_id" in values:
                values["order_id"] = "PED-1001"
            if "desisti" in low and "reason" in values:
                values["reason"] = "desisti da compra"
            if low.strip() == "71,99" and "valor" in values:
                values["valor"] = 71.99
            if low.strip() == "tim music" and "subject" in values:
                values["subject"] = "TIM Music"
            return json.dumps(values, ensure_ascii=False)

        # Router LLM fallback: treat fatura as a real intent shift.
        if "fatura" in prompt.lower():
            return json.dumps({
                "decision": "SHIFT",
                "intent": "billing_invoice_explanation",
                "agent": "billing_agent",
                "confidence": 0.98,
                "reason": "nova intenção de fatura",
            })
        return json.dumps({
            "decision": "CONTINUE",
            "intent": None,
            "agent": None,
            "confidence": 0.95,
            "reason": "continua transação",
        })


class _Router:
    def __init__(self):
        self.registry = SimpleNamespace(
            tools={},
            get_tool=self.get_tool,
        )

    def get_tool(self, name):
        data = {
            "solicitar_devolucao": SimpleNamespace(
                name="solicitar_devolucao",
                description="Abre uma solicitação de devolução de pedido.",
                selection_keywords=["devolver pedido", "devolução", "devolver"],
                args_schema={"order_id": "string", "reason": "string"},
                requires=["order_id", "reason"],
                confirmation_required=True,
                tool_type="action",
            ),
            "cancelar_pedido": SimpleNamespace(
                name="cancelar_pedido",
                description="Cancela um pedido.",
                selection_keywords=["cancelar pedido", "cancelar compra"],
                args_schema={"order_id": "string"},
                requires=["order_id"],
                confirmation_required=True,
                tool_type="action",
            ),
        }
        return data.get(name)

    def resolve_execution_policy(self, tool_name, arguments=None):
        cfg = self.get_tool(tool_name)
        if not cfg:
            return {"operation_type": "read_only", "require_confirmation": False, "requires": []}
        return {
            "operation_type": "transactional",
            "require_confirmation": True,
            "requires": list(cfg.requires),
            "policy_source": "test",
        }

    def parameter_extract_rules(self, tool_name):
        # Deliberately has MCP mappings for the same fields: transactional fields
        # must be excluded from this mechanism by the runtime.
        return {
            "order_id": {"from": "message", "strategy": "regex", "pattern": r"pedido\\s+(\\w+)"},
            "reason": {"from": "message", "strategy": "regex", "pattern": r"motivo\\s+(.+)"},
        }

    def validate_execution_policy(self, tool_name, arguments=None):
        return True, None, self.resolve_execution_policy(tool_name, arguments)


class _Runtime(AgentRuntimeMixin):
    def __init__(self):
        self.tool_router = _Router()
        self.llm = _SemanticLLM()
        self.calls = []

    async def _call_mcp_tool(self, tool_name, arguments, state):
        self.calls.append((tool_name, dict(arguments)))
        return {"ok": True, "tool_name": tool_name, "result": {"status": "OK"}}


@pytest.mark.asyncio
async def test_transaction_extractor_handles_multiple_parameters_without_hardcoded_regex():
    runtime = _Runtime()
    state = {
        "user_text": "quero devolver pedido PED-1001 porque desisti da compra",
        "sanitized_input": "quero devolver pedido PED-1001 porque desisti da compra",
        "mcp_tools": ["solicitar_devolucao"],
        "route": "support_agent",
        "intent": "retail_support_exchange_return",
    }
    result = await runtime.execute_tools_for_intent(state)
    assert result[-1]["awaiting_confirmation"] is True
    assert state["transaction_status"] == "AWAITING_CONFIRMATION"
    args = state["pending_tool_call"]["arguments"]
    assert args["order_id"] == "PED-1001"
    assert args["reason"] == "desisti da compra"


@pytest.mark.asyncio
async def test_collecting_one_parameter_consumes_turn_after_classifier_continues(tmp_path):
    routing = tmp_path / "routing.yaml"
    routing.write_text(
        """
router:
  fallback_agent: support_agent
  confidence_threshold: 0.70
state_policies:
  - state: COLLECTING_SUPPORT_PARAMETERS
    agent: support_agent
intents:
  - name: retail_order_tracking
    agent: orders_agent
    priority: 20
    keywords: [pedido]
  - name: retail_support_exchange_return
    agent: support_agent
    priority: 30
    keywords: [devolver pedido]
  - name: billing_invoice_explanation
    agent: billing_agent
    priority: 40
    keywords: [fatura]
""",
        encoding="utf-8",
    )
    settings = SimpleNamespace(
        ROUTING_CONFIG_PATH=str(routing),
        ENABLE_LLM_ROUTER=True,
        ENABLE_ROUTE_STICKINESS=False,
    )
    router = EnterpriseRouter(settings, llm=_SemanticLLM())
    state = {
        "user_text": "o numero do pedido é PED-1001",
        "sanitized_input": "o numero do pedido é PED-1001",
        "next_state": "COLLECTING_SUPPORT_PARAMETERS",
        "transaction_status": "COLLECTING_PARAMETERS",
        "missing_parameters": ["order_id", "reason"],
        "active_agent": "support_agent",
        "intent": "state:COLLECTING_SUPPORT_PARAMETERS",
        "active_transaction": {
            "tool_name": "solicitar_devolucao",
            "arguments": {},
            "status": "COLLECTING_PARAMETERS",
            "started_from_intent": "retail_support_exchange_return",
            "parameter_schema": {"order_id": "string", "reason": "string"},
            "tool_description": "Abre uma solicitação de devolução de pedido.",
        },
    }
    decision = await router.route(state)
    assert decision.agent == "support_agent"
    assert decision.intent == "state:COLLECTING_SUPPORT_PARAMETERS"
    assert decision.metadata["transaction_turn_consumed"] is True
    assert decision.metadata["transaction_parameter_values"] == {"order_id": "PED-1001"}
    assert "transaction_interruption" not in decision.metadata


@pytest.mark.asyncio
async def test_no_parameter_found_allows_intent_shift(tmp_path):
    routing = tmp_path / "routing.yaml"
    routing.write_text(
        """
router:
  fallback_agent: support_agent
  confidence_threshold: 0.70
state_policies:
  - state: COLLECTING_SUPPORT_PARAMETERS
    agent: support_agent
intents:
  - name: retail_support_exchange_return
    agent: support_agent
    priority: 20
    keywords: [devolver pedido]
  - name: billing_invoice_explanation
    agent: billing_agent
    priority: 40
    keywords: [fatura]
""",
        encoding="utf-8",
    )
    settings = SimpleNamespace(
        ROUTING_CONFIG_PATH=str(routing),
        ENABLE_LLM_ROUTER=True,
        ENABLE_ROUTE_STICKINESS=False,
    )
    router = EnterpriseRouter(settings, llm=_SemanticLLM())
    state = {
        "user_text": "esquece isso, quero ver minha fatura",
        "sanitized_input": "esquece isso, quero ver minha fatura",
        "next_state": "COLLECTING_SUPPORT_PARAMETERS",
        "transaction_status": "COLLECTING_PARAMETERS",
        "missing_parameters": ["order_id", "reason"],
        "active_agent": "support_agent",
        "intent": "state:COLLECTING_SUPPORT_PARAMETERS",
        "active_transaction": {
            "tool_name": "solicitar_devolucao",
            "arguments": {},
            "status": "COLLECTING_PARAMETERS",
            "started_from_intent": "retail_support_exchange_return",
            "parameter_schema": {"order_id": "string", "reason": "string"},
        },
    }
    decision = await router.route(state)
    assert decision.intent == "billing_invoice_explanation"
    assert decision.agent == "billing_agent"
    assert decision.metadata["transaction_interruption"] == "intent_shift"


def test_hardcoded_action_argument_extractor_removed():
    from pathlib import Path
    source = Path("libs/agent_framework/src/agent_framework/runtime/agent_runtime.py").read_text(encoding="utf-8")
    assert "def _extract_action_arguments" not in source
    assert "pedido|ordem" not in source
    assert "reason_match" not in source

@pytest.mark.asyncio
async def test_confirmation_is_consumed_before_intent_shift(tmp_path):
    routing = tmp_path / "routing.yaml"
    routing.write_text(
        """
router:
  fallback_agent: support_agent
  confidence_threshold: 0.70
state_policies:
  - state: WAITING_SUPPORT_CONFIRMATION
    agent: support_agent
intents:
  - name: generic_yes_intent
    agent: other_agent
    priority: 50
    keywords: [sim]
""",
        encoding="utf-8",
    )
    settings = SimpleNamespace(
        ROUTING_CONFIG_PATH=str(routing),
        ENABLE_LLM_ROUTER=True,
        ENABLE_ROUTE_STICKINESS=False,
    )
    router = EnterpriseRouter(settings, llm=_SemanticLLM())
    state = {
        "user_text": "sim",
        "sanitized_input": "sim",
        "next_state": "WAITING_SUPPORT_CONFIRMATION",
        "transaction_status": "AWAITING_CONFIRMATION",
        "active_agent": "support_agent",
        "active_transaction": {
            "tool_name": "solicitar_devolucao",
            "arguments": {"order_id": "PED-1001", "reason": "desisti"},
            "status": "AWAITING_CONFIRMATION",
            "started_from_intent": "retail_support_exchange_return",
        },
    }
    decision = await router.route(state)
    assert decision.agent == "support_agent"
    assert decision.metadata["transaction_turn_consumed"] is True
    assert decision.metadata["transaction_confirmation_decision"] == "confirm"
    assert "transaction_interruption" not in decision.metadata

@pytest.mark.asyncio
async def test_incompatible_intent_shift_wins_even_when_turn_could_fill_pending_parameter(tmp_path):
    """A value-like turn cannot shield an incompatible new goal from intent-shift.

    Regression for the edge case where the active transaction is collecting a
    field, but the same utterance clearly starts another transactional intent.
    The framework must classify the goal first; parameter extraction is allowed
    only after the classifier says CONTINUE.
    """
    routing = tmp_path / "routing.yaml"
    routing.write_text(
        """
router:
  fallback_agent: support_agent
  confidence_threshold: 0.70
state_policies:
  - state: COLLECTING_SUPPORT_PARAMETERS
    agent: support_agent
intents:
  - name: retail_support_exchange_return
    agent: support_agent
    priority: 20
    keywords: [devolver pedido]
  - name: retail_order_cancel
    agent: orders_agent
    priority: 30
    keywords: [cancelar pedido]
""",
        encoding="utf-8",
    )

    class _ShiftAndExtractLLM:
        def __init__(self):
            self.extraction_calls = 0
            self.shift_calls = 0

        async def ainvoke(self, messages, **kwargs):
            prompt = messages[-1]["content"] if isinstance(messages[-1], dict) else str(messages[-1])
            if kwargs.get("profile_name") == "transaction_parameter_extraction" or "pending_parameters:" in prompt:
                self.extraction_calls += 1
                # This demonstrates the dangerous overlap: if extraction ran
                # first, it could consume a field from the same utterance.
                return json.dumps({"reason": "cancelar pedido PED-2002"})
            self.shift_calls += 1
            return json.dumps({
                "decision": "SHIFT",
                "intent": "retail_order_cancel",
                "agent": "orders_agent",
                "confidence": 0.99,
                "reason": "usuário passou a cancelar outro pedido",
            })

    llm = _ShiftAndExtractLLM()
    settings = SimpleNamespace(
        ROUTING_CONFIG_PATH=str(routing),
        ENABLE_LLM_ROUTER=True,
        ENABLE_ROUTE_STICKINESS=False,
    )
    router = EnterpriseRouter(settings, llm=llm)
    state = {
        "user_text": "agora quero cancelar pedido PED-2002",
        "sanitized_input": "agora quero cancelar pedido PED-2002",
        "next_state": "COLLECTING_SUPPORT_PARAMETERS",
        "transaction_status": "COLLECTING_PARAMETERS",
        "missing_parameters": ["reason"],
        "active_agent": "support_agent",
        "intent": "state:COLLECTING_SUPPORT_PARAMETERS",
        "active_transaction": {
            "tool_name": "solicitar_devolucao",
            "arguments": {"order_id": "PED-1001"},
            "status": "COLLECTING_PARAMETERS",
            "started_from_intent": "retail_support_exchange_return",
            "parameter_schema": {"reason": "string"},
        },
    }

    decision = await router.route(state)

    assert decision.intent == "retail_order_cancel"
    assert decision.agent == "orders_agent"
    assert decision.metadata["transaction_interruption"] == "intent_shift"
    assert llm.shift_calls == 1
    assert llm.extraction_calls == 0


@pytest.mark.asyncio
async def test_semantic_shift_wins_before_parameter_extraction_when_no_keyword_matches(tmp_path):
    """Semantic SHIFT must win even if extraction could return a pending field."""
    routing = tmp_path / "routing.yaml"
    routing.write_text(
        """
router:
  fallback_agent: support_agent
  confidence_threshold: 0.70
state_policies:
  - state: COLLECTING_SUPPORT_PARAMETERS
    agent: support_agent
intents:
  - name: retail_support_exchange_return
    agent: support_agent
    priority: 20
    keywords: [devolver pedido]
  - name: retail_order_cancel
    agent: orders_agent
    priority: 30
    keywords: []
""",
        encoding="utf-8",
    )

    class _SemanticShiftAndExtractLLM:
        def __init__(self):
            self.extraction_calls = 0
            self.shift_calls = 0

        async def ainvoke(self, messages, **kwargs):
            prompt = messages[-1]["content"] if isinstance(messages[-1], dict) else str(messages[-1])
            if kwargs.get("profile_name") == "transaction_parameter_extraction" or "pending_parameters:" in prompt:
                self.extraction_calls += 1
                return json.dumps({"reason": "encerrar a compra"})
            self.shift_calls += 1
            return json.dumps({
                "decision": "SHIFT",
                "intent": "retail_order_cancel",
                "agent": "orders_agent",
                "confidence": 0.98,
                "reason": "novo objetivo transacional incompatível",
            })

    llm = _SemanticShiftAndExtractLLM()
    settings = SimpleNamespace(
        ROUTING_CONFIG_PATH=str(routing),
        ENABLE_LLM_ROUTER=True,
        ENABLE_ROUTE_STICKINESS=False,
    )
    router = EnterpriseRouter(settings, llm=llm)
    state = {
        "user_text": "mudei de ideia, quero encerrar a compra PED-2002",
        "sanitized_input": "mudei de ideia, quero encerrar a compra PED-2002",
        "next_state": "COLLECTING_SUPPORT_PARAMETERS",
        "transaction_status": "COLLECTING_PARAMETERS",
        "missing_parameters": ["reason"],
        "active_agent": "support_agent",
        "intent": "state:COLLECTING_SUPPORT_PARAMETERS",
        "active_transaction": {
            "tool_name": "solicitar_devolucao",
            "arguments": {"order_id": "PED-1001"},
            "status": "COLLECTING_PARAMETERS",
            "started_from_intent": "retail_support_exchange_return",
            "parameter_schema": {"reason": "string"},
        },
    }

    decision = await router.route(state)

    assert decision.intent == "retail_order_cancel"
    assert decision.agent == "orders_agent"
    assert decision.metadata["transaction_interruption"] == "intent_shift"
    assert decision.metadata["interruption_source"] == "semantic_classifier"
    assert llm.shift_calls == 1
    assert llm.extraction_calls == 0
