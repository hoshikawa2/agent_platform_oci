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
