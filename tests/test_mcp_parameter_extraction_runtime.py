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

class _ContestExtractLLM:
    async def ainvoke(self, messages, **kwargs):
        prompt = messages[0]["content"]
        if "Campo: subject" in prompt:
            return {"content": '{"subject": "TIM CTRL Redes Sociais 8.0"}'}
        if "Campo: valor" in prompt:
            return {"content": '{"valor": null}'}
        return {"content": '{}'}


class _ContestExtractRouter:
    def parameter_extract_rules(self, tool_name):
        return {
            "subject": {
                "from": "message",
                "strategy": "llm",
                "type": "string",
                "description": "Extraia o item contestado.",
            },
            "valor": {
                "from": "message",
                "strategy": "llm",
                "type": "number",
                "description": "Extraia o valor explicitamente informado.",
            },
        }


class _ContestExtractRuntime(AgentRuntimeMixin):
    def __init__(self):
        self.tool_router = _ContestExtractRouter()
        self.llm = _ContestExtractLLM()


@pytest.mark.asyncio
async def test_new_transaction_current_message_overrides_stale_subject_from_context():
    runtime = _ContestExtractRuntime()
    result = await runtime._extract_mcp_parameters(
        "contestar_cobranca",
        {"subject": "TIM Fashion Mensal", "valor": 10.0},
        {
            "user_text": "nao contratei TIM CTRL Redes Sociais 8.0",
            "sanitized_input": "nao contratei TIM CTRL Redes Sociais 8.0",
        },
        overwrite_from_message=True,
    )
    assert result["subject"] == "TIM CTRL Redes Sociais 8.0"
    # null extraction does not destroy a pre-existing value; transaction start
    # sanitization is about explicit current-message evidence, not blind clearing.
    assert result["valor"] == 10.0
