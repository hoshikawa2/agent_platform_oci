from types import SimpleNamespace

import pytest

from agent_framework.routing.enterprise_router import EnterpriseRouter
from agent_framework.runtime.agent_runtime import AgentRuntimeMixin


ROUTING_YAML = """
router:
  fallback_agent: billing_agent
  confidence_threshold: 0.70
state_policies:
  - state: COLLECTING_ORDER_PARAMETERS
    agent: orders_agent
  - state: WAITING_ORDER_CONFIRMATION
    agent: orders_agent
intents:
  - name: retail_order_cancel
    domain: retail
    agent: orders_agent
    priority: 30
    keywords: [cancelar pedido]
  - name: retail_order_tracking
    domain: retail
    agent: orders_agent
    priority: 20
    keywords: [rastrear pedido, pedido]
  - name: billing_invoice_explanation
    domain: telecom
    agent: billing_agent
    priority: 40
    keywords: [fatura, vencimento]
"""


class _ParameterLLM:
    async def ainvoke(self, messages, **kwargs):
        import json
        prompt = messages[-1]["content"]
        if kwargs.get("profile_name") == "transaction_parameter_extraction":
            pending = json.loads(prompt.split("pending_parameters: ", 1)[1].split("\n", 1)[0])
            user = prompt.split("user_message: ", 1)[1].split("\nFormato obrigatório:", 1)[0].strip()
            out = {name: None for name in pending}
            if len(pending) == 1 and user not in {"quero rastrear pedido", "quero ver minha fatura"}:
                out[pending[0]] = user
            return json.dumps(out, ensure_ascii=False)
        return '{}'


def _router(tmp_path, *, stickiness=True):
    routing = tmp_path / "routing.yaml"
    routing.write_text(ROUTING_YAML, encoding="utf-8")
    settings = SimpleNamespace(
        ROUTING_CONFIG_PATH=str(routing),
        ENABLE_LLM_ROUTER=False,
        ENABLE_ROUTE_STICKINESS=stickiness,
    )
    return EnterpriseRouter(settings, llm=_ParameterLLM())


def _active_tx(status="COLLECTING_PARAMETERS", arguments=None):
    return {
        "tool_name": "cancelar_pedido",
        "status": status,
        "started_from_intent": "retail_order_cancel",
        "arguments": dict(arguments or {"order_id": "PED-1001"}),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["PED-1001", "o pedido é o PED-1001", "12345", "R$ 71,99", "10/09/2026"])
async def test_matrix_collecting_parameter_answers_keep_transaction(message, tmp_path):
    router = _router(tmp_path)
    state = {
        "user_text": message,
        "sanitized_input": message,
        "next_state": "COLLECTING_ORDER_PARAMETERS",
        "transaction_status": "COLLECTING_PARAMETERS",
        "missing_parameters": ["order_id"],
        "active_transaction": _active_tx(arguments={}),
        "active_agent": "orders_agent",
        "intent": "state:COLLECTING_ORDER_PARAMETERS",
        "route_decision": {"agent": "orders_agent", "intent": "retail_order_cancel"},
    }
    decision = await router.route(state)
    assert decision.method == "state"
    assert decision.agent == "orders_agent"
    assert (decision.metadata or {}).get("transaction_interruption") is None


@pytest.mark.asyncio
async def test_matrix_specific_same_agent_intent_shift_still_preempts_collection(tmp_path):
    router = _router(tmp_path)
    state = {
        "user_text": "quero rastrear pedido",
        "sanitized_input": "quero rastrear pedido",
        "next_state": "COLLECTING_ORDER_PARAMETERS",
        "transaction_status": "COLLECTING_PARAMETERS",
        "missing_parameters": ["order_id"],
        "active_transaction": _active_tx(arguments={}),
        "active_agent": "orders_agent",
        "intent": "state:COLLECTING_ORDER_PARAMETERS",
        "route_decision": {"agent": "orders_agent", "intent": "retail_order_cancel"},
    }
    decision = await router.route(state)
    assert decision.intent == "retail_order_tracking"
    assert decision.metadata["transaction_interruption"] == "intent_shift"


@pytest.mark.asyncio
async def test_matrix_missing_next_state_recovers_active_transaction_before_stickiness(tmp_path):
    router = _router(tmp_path)
    state = {
        "user_text": "PED-1001",
        "sanitized_input": "PED-1001",
        "next_state": None,
        "transaction_status": "COLLECTING_PARAMETERS",
        "missing_parameters": ["order_id"],
        "selected_tool_call": {"tool_name": "cancelar_pedido", "arguments": {}},
        "active_transaction": _active_tx(arguments={}),
        "active_agent": "orders_agent",
        "route": "orders_agent",
        "route_decision": {"agent": "orders_agent", "intent": "retail_order_cancel"},
    }
    decision = await router.route(state)
    assert decision.method == "state"
    assert decision.metadata["transaction_state_recovered"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    ["COMPLETED", "FAILED", "CANCELLED", "BLOCKED", "OUT_OF_SCOPE"],
)
async def test_matrix_terminal_transaction_never_recovers_from_latch(status, tmp_path):
    router = _router(tmp_path, stickiness=False)
    state = {
        "user_text": "quero ver minha fatura",
        "sanitized_input": "quero ver minha fatura",
        "next_state": None,
        "transaction_status": status,
        # Deliberately stale latch: terminal status must win.
        "active_transaction": _active_tx(status=status),
        "selected_tool_call": {"tool_name": "cancelar_pedido", "arguments": {"order_id": "PED-1001"}},
        "active_agent": "orders_agent",
        "intent": "retail_order_cancel",
        "route_decision": {"agent": "orders_agent", "intent": "retail_order_cancel"},
    }
    decision = await router.route(state)
    assert decision.intent == "billing_invoice_explanation"
    assert (decision.metadata or {}).get("transaction_state_recovered") is not True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    ["COMPLETED", "FAILED", "CANCELLED", "BLOCKED", "OUT_OF_SCOPE"],
)
async def test_matrix_terminal_transaction_ignores_stale_next_state(status, tmp_path):
    router = _router(tmp_path, stickiness=False)
    state = {
        "user_text": "quero ver minha fatura",
        "sanitized_input": "quero ver minha fatura",
        # Simulate a partially persisted/legacy state where terminal status was
        # written but the transactional next_state was not cleared.
        "next_state": "COLLECTING_ORDER_PARAMETERS",
        "transaction_status": status,
        "active_transaction": _active_tx(status=status),
        "active_agent": "orders_agent",
        "intent": "retail_order_cancel",
        "route_decision": {"agent": "orders_agent", "intent": "retail_order_cancel"},
    }
    decision = await router.route(state)
    assert decision.intent == "billing_invoice_explanation"
    assert decision.agent == "billing_agent"
    assert decision.method != "state"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,next_state",
    [
        ("COLLECTING_PARAMETERS", "COLLECTING_ORDER_PARAMETERS"),
        ("AWAITING_CONFIRMATION", "WAITING_ORDER_CONFIRMATION"),
    ],
)
async def test_matrix_clear_intent_shift_preempts_active_transaction(status, next_state, tmp_path):
    router = _router(tmp_path)
    state = {
        "user_text": "esquece, quero ver minha fatura",
        "sanitized_input": "esquece, quero ver minha fatura",
        "next_state": next_state,
        "transaction_status": status,
        "active_transaction": _active_tx(status=status),
        "active_agent": "orders_agent",
        "intent": f"state:{next_state}",
        "route_decision": {"agent": "orders_agent", "intent": "retail_order_cancel"},
    }
    decision = await router.route(state)
    assert decision.intent == "billing_invoice_explanation"
    assert decision.agent == "billing_agent"
    assert decision.metadata["transaction_interruption"] == "intent_shift"


@pytest.mark.asyncio
async def test_matrix_route_stickiness_without_transaction_preserves_previous_behavior(tmp_path):
    router = _router(tmp_path)
    # Generic short follow-up: no transaction latch, no explicit new intent.
    state = {
        "user_text": "e o status?",
        "sanitized_input": "e o status?",
        "next_state": None,
        "transaction_status": None,
        "active_transaction": None,
        "active_agent": "orders_agent",
        "intent": "retail_order_tracking",
        "route_decision": {
            "route": "orders_agent",
            "agent": "orders_agent",
            "intent": "retail_order_tracking",
            "domain": "retail",
            "mcp_tools": [],
        },
        "context": {"session": {}},
    }
    decision = await router.route(state)
    # Semantic continuity may be disabled by settings/profile defaults in the
    # isolated test; regardless, transaction recovery must not be involved.
    assert (decision.metadata or {}).get("transaction_state_recovered") is not True


class _PolicyRouter:
    def __init__(self):
        self.registry = SimpleNamespace(
            tools={"cancelar_pedido": object()},
            get_tool=lambda name: SimpleNamespace(selection_keywords=["cancelar pedido", "cancelar"]),
        )

    def resolve_execution_policy(self, tool_name, arguments=None):
        return {
            "operation_type": "transactional",
            "require_confirmation": True,
            "requires": ["order_id"],
            "policy_source": "matrix-test",
        }

    def validate_execution_policy(self, tool_name, arguments=None):
        return True, None, self.resolve_execution_policy(tool_name, arguments)


class _Runtime(AgentRuntimeMixin):
    def __init__(self, *, call_ok=True):
        self.tool_router = _PolicyRouter()
        self.calls = []
        self.call_ok = call_ok

    async def _call_mcp_tool(self, tool_name, arguments, state):
        self.calls.append((tool_name, dict(arguments)))
        return {"ok": self.call_ok, "tool_name": tool_name, "result": {"status": "DONE" if self.call_ok else "ERROR"}}


@pytest.mark.asyncio
async def test_matrix_confirmation_yes_completes_and_clears_latches():
    runtime = _Runtime(call_ok=True)
    state = {
        "user_text": "sim",
        "sanitized_input": "sim",
        "transaction_status": "AWAITING_CONFIRMATION",
        "active_transaction": _active_tx(status="AWAITING_CONFIRMATION"),
        "pending_tool_call": {"tool_name": "cancelar_pedido", "arguments": {"order_id": "PED-1001"}},
    }
    result = await runtime.execute_tools_for_intent(state, tools=[])
    assert result[-1]["ok"] is True
    assert state["transaction_status"] == "COMPLETED"
    assert state["active_transaction"] is None
    assert state["next_state"] is None


@pytest.mark.asyncio
async def test_matrix_confirmation_no_cancels_and_clears_latches():
    runtime = _Runtime(call_ok=True)
    state = {
        "user_text": "não",
        "sanitized_input": "não",
        "transaction_status": "AWAITING_CONFIRMATION",
        "active_transaction": _active_tx(status="AWAITING_CONFIRMATION"),
        "pending_tool_call": {"tool_name": "cancelar_pedido", "arguments": {"order_id": "PED-1001"}},
    }
    result = await runtime.execute_tools_for_intent(state, tools=[])
    assert result[-1]["transaction_status"] == "CANCELLED"
    assert state["transaction_status"] == "CANCELLED"
    assert state["active_transaction"] is None
    assert state["next_state"] is None
    assert runtime.calls == []


@pytest.mark.asyncio
async def test_matrix_runtime_does_not_cancel_from_literal_words_without_intent_shift():
    runtime = _Runtime(call_ok=True)
    state = {
        "user_text": "texto livre sem classificação de nova intent",
        "sanitized_input": "texto livre sem classificação de nova intent",
        "transaction_status": "COLLECTING_PARAMETERS",
        "active_transaction": _active_tx(status="COLLECTING_PARAMETERS", arguments={}),
        "selected_tool_call": {"tool_name": "cancelar_pedido", "arguments": {}},
        "missing_parameters": ["order_id"],
    }
    await runtime.execute_tools_for_intent(state, tools=[])
    assert state["transaction_status"] != "CANCELLED"
    assert state["active_transaction"] is not None


@pytest.mark.asyncio
async def test_matrix_intent_shift_cancels_old_transaction_before_new_tool_path():
    runtime = _Runtime(call_ok=True)
    state = {
        "user_text": "quero ver minha fatura",
        "sanitized_input": "quero ver minha fatura",
        "transaction_status": "COLLECTING_PARAMETERS",
        "active_transaction": _active_tx(status="COLLECTING_PARAMETERS", arguments={}),
        "selected_tool_call": {"tool_name": "cancelar_pedido", "arguments": {}},
        "missing_parameters": ["order_id"],
        "route_decision": {"metadata": {"transaction_interruption": "intent_shift"}},
    }
    await runtime.execute_tools_for_intent(state, tools=[])
    assert state["transaction_status"] == "CANCELLED"
    assert state["active_transaction"] is None
    assert state["tool_policy_result"]["action"] == "cancelled_by_intent_shift"


@pytest.mark.asyncio
async def test_matrix_intent_shift_clears_arguments_and_restart_starts_from_zero():
    runtime = _Runtime(call_ok=True)
    state = {
        "user_text": "nova intenção",
        "sanitized_input": "nova intenção",
        "transaction_status": "COLLECTING_PARAMETERS",
        "active_transaction": _active_tx(
            status="COLLECTING_PARAMETERS",
            arguments={"order_id": "PED-OLD"},
        ),
        "selected_tool_call": {
            "tool_name": "cancelar_pedido",
            "arguments": {"order_id": "PED-OLD"},
        },
        "pending_tool_call": {
            "tool_name": "cancelar_pedido",
            "arguments": {"order_id": "PED-OLD"},
        },
        "missing_parameters": [],
        "route_decision": {"metadata": {"transaction_interruption": "intent_shift"}},
    }
    await runtime.execute_tools_for_intent(state, tools=[])

    assert state["transaction_status"] == "CANCELLED"
    assert state["active_transaction"] is None
    assert state["selected_tool_call"] == {}
    assert state["pending_tool_call"] == {}
    assert state["missing_parameters"] == []
    assert state["next_state"] is None
    assert state["last_transaction"]["arguments"] == {"order_id": "PED-OLD"}

    # Se a intent antiga voltar depois, o histórico fica apenas em last_transaction;
    # nenhum argumento operacional é restaurado para a nova transação.
    state["transaction_status"] = None
    state["route_decision"] = {}
    state["user_text"] = "iniciar novamente"
    state["sanitized_input"] = "iniciar novamente"
    state["mcp_tools"] = ["cancelar_pedido"]
    await runtime.execute_tools_for_intent(state, tools=["cancelar_pedido"])
    assert state.get("selected_tool_call", {}).get("arguments", {}).get("order_id") != "PED-OLD"
    assert (state.get("active_transaction") or {}).get("arguments", {}).get("order_id") != "PED-OLD"


@pytest.mark.asyncio
async def test_matrix_tool_failure_is_terminal_and_not_reactivated():
    runtime = _Runtime(call_ok=False)
    state = {
        "user_text": "sim",
        "sanitized_input": "sim",
        "transaction_status": "AWAITING_CONFIRMATION",
        "active_transaction": _active_tx(status="AWAITING_CONFIRMATION"),
        "pending_tool_call": {"tool_name": "cancelar_pedido", "arguments": {"order_id": "PED-1001"}},
    }
    await runtime.execute_tools_for_intent(state, tools=[])
    assert state["transaction_status"] == "FAILED"
    assert state["active_transaction"] is None
    assert state["pending_tool_call"] == {}
    assert state["next_state"] is None


@pytest.mark.parametrize("status", ["COMPLETED", "FAILED", "CANCELLED", "BLOCKED", "OUT_OF_SCOPE"])
def test_matrix_normalization_clears_terminal_operational_latches(status):
    runtime = _Runtime()
    state = {
        "transaction_status": status,
        "next_state": "COLLECTING_ORDER_PARAMETERS",
        "active_transaction": _active_tx(status=status),
        "selected_tool_call": {"tool_name": "cancelar_pedido", "arguments": {"order_id": "PED-1001"}},
        "pending_tool_call": {"tool_name": "cancelar_pedido", "arguments": {"order_id": "PED-1001"}},
        "missing_parameters": ["order_id"],
        "confirmation_required": True,
    }
    runtime._normalize_transaction_lifecycle(state)
    assert state["active_transaction"] is None
    assert state["selected_tool_call"] == {}
    assert state["pending_tool_call"] == {}
    assert state["missing_parameters"] == []
    assert state["next_state"] is None
    assert state["last_transaction"]["status"] == status

@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["COMPLETED", "FAILED", "CANCELLED", "BLOCKED", "OUT_OF_SCOPE"])
async def test_matrix_terminal_stale_next_state_does_not_lock_generic_followup(status, tmp_path):
    router = _router(tmp_path, stickiness=False)
    state = {
        "user_text": "ok",
        "sanitized_input": "ok",
        "next_state": "COLLECTING_ORDER_PARAMETERS",
        "transaction_status": status,
        "active_transaction": _active_tx(status=status),
        "active_agent": "orders_agent",
        "intent": "retail_order_cancel",
        "route_decision": {"agent": "orders_agent", "intent": "retail_order_cancel"},
        "context": {"session": {}},
    }
    decision = await router.route(state)
    assert decision.method != "state"
    assert (decision.metadata or {}).get("transaction_state_recovered") is not True
