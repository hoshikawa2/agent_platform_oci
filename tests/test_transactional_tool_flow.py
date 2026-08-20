from pathlib import Path

from agent_framework.mcp.tool_policy import ToolPolicyRegistry


def test_tool_policy_registry_reads_transactional_confirmation(tmp_path: Path):
    config = tmp_path / "tool_policies.yaml"
    config.write_text("""version: 1
defaults:
  operation_type: read_only
  require_confirmation: false
tool_policies:
  solicitar_devolucao:
    operation_type: transactional
    require_confirmation: true
""", encoding="utf-8")
    policy = ToolPolicyRegistry(str(config)).get("solicitar_devolucao")
    assert policy is not None
    assert policy.operation_type == "transactional"
    assert policy.require_confirmation is True


def test_runtime_source_contains_persisted_confirmation_contract():
    source = Path("libs/agent_framework/src/agent_framework/runtime/agent_runtime.py").read_text(encoding="utf-8")
    assert "pending_tool_call" in source
    assert "AWAITING_CONFIRMATION" in source
    assert "executed_after_confirmation" in source

import pytest
from agent_framework.runtime.agent_runtime import AgentRuntimeMixin


class _PolicyRouter:
    def __init__(self):
        from types import SimpleNamespace
        self.registry = SimpleNamespace(
            tools={"consultar_pedido": object(), "solicitar_devolucao": object()},
            get_tool=lambda name: {
                "consultar_pedido": SimpleNamespace(selection_keywords=["consultar pedido", "pedido"]),
                "solicitar_devolucao": SimpleNamespace(selection_keywords=["devolver pedido", "devolver", "devolução", "arrependimento"]),
            }.get(name),
        )

    def resolve_execution_policy(self, tool_name, arguments=None):
        if tool_name == "solicitar_devolucao":
            return {"operation_type": "transactional", "require_confirmation": True, "policy_source": "test"}
        return {"operation_type": "read_only", "require_confirmation": False, "policy_source": "test"}

    def validate_execution_policy(self, tool_name, arguments=None):
        policy = self.resolve_execution_policy(tool_name, arguments)
        if policy["require_confirmation"] and not (arguments or {}).get("confirmed"):
            return False, "Tool exige confirmação explícita antes da execução", policy
        return True, None, policy


class _Runtime(AgentRuntimeMixin):
    def __init__(self):
        self.tool_router = _PolicyRouter()
        self.calls = []

    async def _call_mcp_tool(self, tool_name, arguments, state):
        self.calls.append((tool_name, dict(arguments)))
        return {"ok": True, "tool_name": tool_name, "result": {"status": "ABERTO"}}


@pytest.mark.asyncio
async def test_transaction_waits_then_executes_after_confirmation():
    runtime = _Runtime()
    state = {
        "user_text": "Quero devolver o pedido 123 porque me arrependi",
        "sanitized_input": "Quero devolver o pedido 123 porque me arrependi",
        "mcp_tools": ["consultar_pedido", "solicitar_devolucao"],
        "route": "support_agent",
        "intent": "retail_support_exchange_return",
    }
    first = await runtime.execute_tools_for_intent(state)
    assert state["transaction_status"] == "AWAITING_CONFIRMATION"
    assert state["pending_tool_call"]["tool_name"] == "solicitar_devolucao"
    assert state["pending_tool_call"]["arguments"]["order_id"] == "123"
    assert not any(name == "solicitar_devolucao" for name, _ in runtime.calls)
    assert first[-1]["awaiting_confirmation"] is True

    state["user_text"] = "Sim, confirmo a devolução."
    state["sanitized_input"] = state["user_text"]
    second = await runtime.execute_tools_for_intent(state)
    assert state["transaction_status"] == "COMPLETED"
    assert state["pending_tool_call"] == {}
    assert runtime.calls[-1][0] == "solicitar_devolucao"
    assert runtime.calls[-1][1]["confirmed"] is True
    assert second[-1]["ok"] is True

class _ContestPolicyRouter:
    def __init__(self):
        from types import SimpleNamespace
        self.registry = SimpleNamespace(
            tools={"contestar_cobranca": object()},
            get_tool=lambda name: SimpleNamespace(selection_keywords=["contestar", "não contratei", "nao contratei"]),
        )

    def resolve_execution_policy(self, tool_name, arguments=None):
        return {
            "operation_type": "transactional",
            "require_confirmation": True,
            "requires": ["subject", "valor"],
            "policy_source": "test",
        }

    def validate_execution_policy(self, tool_name, arguments=None):
        policy = self.resolve_execution_policy(tool_name, arguments)
        return True, None, policy


class _ContestRuntime(AgentRuntimeMixin):
    def __init__(self):
        self.tool_router = _ContestPolicyRouter()
        self.calls = []

    async def _call_mcp_tool(self, tool_name, arguments, state):
        self.calls.append((tool_name, dict(arguments)))
        return {"ok": True, "tool_name": tool_name, "result": {"status": "OPENED"}}


@pytest.mark.asyncio
async def test_collecting_parameters_does_not_replace_collected_subject_with_stale_context():
    """A later value-only turn must not replace an already collected subject.

    Regression reproduced from Contas: subject was collected as TIM CTRL, while
    context/tool_arguments still exposed TIM Fashion from another transaction.
    When the user supplied only R$ 71,99, the stale context used to overwrite
    the collected subject before confirmation.
    """
    runtime = _ContestRuntime()
    state = {
        "user_text": "R$ 71,99",
        "sanitized_input": "R$ 71,99",
        "route": "contestacao_agent",
        "intent": "state:COLLECTING_CONTESTACAO_PARAMETERS",
        "transaction_status": "COLLECTING_PARAMETERS",
        "selected_tool_call": {
            "tool_name": "contestar_cobranca",
            "arguments": {
                "subject": "TIM CTRL Redes Sociais 8.0",
                "motivo": "não contratei",
            },
        },
        # Simulates stale contextual arguments left by another action/session turn.
        "context": {
            "tool_arguments": {
                "subject": "TIM Fashion Mensal",
                "valor": 71.99,
            }
        },
    }

    result = await runtime.execute_tools_for_intent(state, tools=[])

    assert result[-1]["transaction_status"] == "AWAITING_CONFIRMATION"
    assert state["pending_tool_call"]["arguments"]["subject"] == "TIM CTRL Redes Sociais 8.0"
    assert state["pending_tool_call"]["arguments"]["valor"] == 71.99
    assert state["pending_tool_call"]["arguments"]["motivo"] == "não contratei"
    assert state["pending_tool_call"]["arguments"]["query"] == "R$ 71,99"
    assert runtime.calls == []

class _InitialContestLLM:
    async def ainvoke(self, messages, **kwargs):
        prompt = messages[0]["content"]
        if "Campo: subject" in prompt:
            return {"content": '{"subject": "TIM CTRL Redes Sociais 8.0"}'}
        if "Campo: valor" in prompt:
            return {"content": '{"valor": null}'}
        if "Campo: motivo" in prompt:
            return {"content": '{"motivo": "não contratei"}'}
        return {"content": '{}'}


class _InitialContestRouter(_ContestPolicyRouter):
    def resolve_execution_policy(self, tool_name, arguments=None):
        return {
            "operation_type": "transactional",
            "require_confirmation": True,
            "requires": ["subject"],
            "policy_source": "test",
        }

    def parameter_extract_rules(self, tool_name):
        return {
            "subject": {"from": "message", "strategy": "llm", "type": "string", "description": "item"},
            "valor": {"from": "message", "strategy": "llm", "type": "number", "description": "valor"},
            "motivo": {"from": "message", "strategy": "llm", "type": "string", "description": "motivo"},
        }


class _InitialContestRuntime(AgentRuntimeMixin):
    def __init__(self):
        self.tool_router = _InitialContestRouter()
        self.llm = _InitialContestLLM()
        self.calls = []

    async def _call_mcp_tool(self, tool_name, arguments, state):
        self.calls.append((tool_name, dict(arguments)))
        return {"ok": True, "tool_name": tool_name, "result": {"status": "OPENED"}}


@pytest.mark.asyncio
async def test_new_contestation_does_not_inherit_subject_or_value_from_previous_transaction():
    runtime = _InitialContestRuntime()
    state = {
        "user_text": "nao contratei TIM CTRL Redes Sociais 8.0",
        "sanitized_input": "nao contratei TIM CTRL Redes Sociais 8.0",
        "mcp_tools": ["contestar_cobranca"],
        "route": "contestacao_agent",
        "intent": "contas_contestation",
        "context": {
            "tool_arguments": {
                "subject": "TIM Fashion Mensal",
                "valor": 10.0,
                "motivo": "contestação antiga",
            }
        },
    }

    result = await runtime.execute_tools_for_intent(state)
    pending = state["pending_tool_call"]["arguments"]
    assert result[-1]["transaction_status"] == "AWAITING_CONFIRMATION"
    assert pending["subject"] == "TIM CTRL Redes Sociais 8.0"
    assert pending["motivo"] == "não contratei"
    assert "valor" not in pending
    assert runtime.calls == []

@pytest.mark.asyncio
async def test_closed_transaction_is_not_operational_context_for_next_turn():
    runtime = _InitialContestRuntime()
    state = {
        "user_text": "nao contratei TIM CTRL Redes Sociais 8.0",
        "sanitized_input": "nao contratei TIM CTRL Redes Sociais 8.0",
        "mcp_tools": ["contestar_cobranca"],
        "route": "contestacao_agent",
        "intent": "contas_contestation",
        # Historical/closed transaction must never feed the new one.
        "transaction_status": "COMPLETED",
        "selected_tool_call": {
            "tool_name": "cancelar_vas_avulso",
            "arguments": {"subject": "TIM Fashion Mensal", "valor": 10.0},
        },
        "pending_tool_call": {},
        "context": {
            "tool_arguments": {
                "subject": "TIM Fashion Mensal",
                "valor": 10.0,
            }
        },
    }

    result = await runtime.execute_tools_for_intent(state)

    assert result[-1]["transaction_status"] == "AWAITING_CONFIRMATION"
    assert state["active_transaction"]["tool_name"] == "contestar_cobranca"
    assert state["active_transaction"]["arguments"]["subject"] == "TIM CTRL Redes Sociais 8.0"
    assert state["pending_tool_call"]["tool_name"] == "contestar_cobranca"
    assert state["pending_tool_call"]["arguments"]["subject"] == "TIM CTRL Redes Sociais 8.0"
    assert state["last_transaction"]["tool_name"] == "cancelar_vas_avulso"
    assert state["last_transaction"]["arguments"]["subject"] == "TIM Fashion Mensal"


@pytest.mark.asyncio
async def test_terminal_confirmation_closes_active_transaction_and_clears_latches():
    runtime = _Runtime()
    state = {
        "user_text": "Quero devolver o pedido 123 porque me arrependi",
        "sanitized_input": "Quero devolver o pedido 123 porque me arrependi",
        "mcp_tools": ["consultar_pedido", "solicitar_devolucao"],
        "route": "support_agent",
        "intent": "retail_support_exchange_return",
    }
    await runtime.execute_tools_for_intent(state)
    assert state["active_transaction"]["status"] == "AWAITING_CONFIRMATION"

    state["user_text"] = "sim"
    state["sanitized_input"] = "sim"
    await runtime.execute_tools_for_intent(state)

    assert state["transaction_status"] == "COMPLETED"
    assert state["active_transaction"] is None
    assert state["selected_tool_call"] == {}
    assert state["pending_tool_call"] == {}
    assert state["missing_parameters"] == []
    assert state["next_state"] is None
    assert state["last_transaction"]["tool_name"] == "solicitar_devolucao"
    assert state["last_transaction"]["status"] == "COMPLETED"
