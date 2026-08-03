import pytest
from agent_framework.identity.mcp_mapper import MCPParameterMapper
from agent_framework.runtime.agent_runtime import AgentRuntimeMixin


def test_explicit_order_id_has_precedence_over_contract_key():
    mapper = MCPParameterMapper({
        "mcp_parameter_mapping": {
            "tools": {
                "consultar_pedido": {
                    "map": {"contract_key": "order_id", "customer_key": "customer_id"},
                    "extract": {"order_id": {"from": "message", "strategy": "llm", "type": "string"}},
                }
            }
        }
    })
    mapped = mapper.map(
        "consultar_pedido",
        {"contract_key": "3000131180", "customer_key": "11999999999"},
        extra_args={"order_id": "123"},
    )
    assert mapped["order_id"] == "123"
    assert mapped["customer_id"] == "11999999999"
    assert "extract" not in mapped


class _FakeLLM:
    async def ainvoke(self, messages, **kwargs):
        assert "consultar pedido 123" in messages[0]["content"]
        assert kwargs["generation_name"] == "llm.mcp_parameter_extraction"
        return {"content": '{"order_id": "123"}'}


class _FakeRouter:
    def parameter_extract_rules(self, tool_name):
        return {
            "order_id": {
                "from": "message",
                "strategy": "llm",
                "type": "string",
                "description": "Extraia o identificador do pedido.",
            }
        }


class _Runtime(AgentRuntimeMixin):
    def __init__(self):
        self.tool_router = _FakeRouter()
        self.llm = _FakeLLM()


@pytest.mark.asyncio
async def test_runtime_extracts_order_id_from_current_message():
    runtime = _Runtime()
    result = await runtime._extract_mcp_parameters(
        "consultar_pedido",
        {"contract_key": "3000131180"},
        {"user_text": "consultar pedido 123", "sanitized_input": "consultar pedido 123"},
    )
    assert result["order_id"] == "123"
    assert result["contract_key"] == "3000131180"
