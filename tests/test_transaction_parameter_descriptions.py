from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agent_framework.runtime.agent_runtime import AgentRuntimeMixin
from agent_framework.runtime.transaction_parameters import extract_transaction_parameters


class _Router:
    def __init__(self, tool, rules=None):
        self.registry = SimpleNamespace(get_tool=lambda name: tool if name == "tx_tool" else None)
        self._rules = rules or {}

    def parameter_extract_rules(self, tool_name):
        return dict(self._rules)


class _Runtime(AgentRuntimeMixin):
    def __init__(self, tool, rules=None):
        self.tool_router = _Router(tool, rules)


class _CaptureLLM:
    def __init__(self):
        self.prompt = ""

    async def ainvoke(self, messages, **kwargs):
        self.prompt = messages[-1]["content"]
        return json.dumps({"subject": "TIM CTRL Redes Sociais 8.0", "valor": None}, ensure_ascii=False)


def test_legacy_args_schema_remains_unchanged_without_description():
    tool = SimpleNamespace(args_schema={"subject": "string", "valor": "number"}, requires=["subject", "valor"])
    runtime = _Runtime(tool)

    schema = runtime._transaction_parameter_schema("tx_tool", {"requires": ["subject", "valor"]})

    assert schema == {"subject": "string", "valor": "number"}


def test_legacy_args_schema_is_enriched_from_mcp_mapping_description():
    tool = SimpleNamespace(args_schema={"subject": "string", "valor": "number"}, requires=["subject", "valor"])
    runtime = _Runtime(
        tool,
        {
            "subject": {
                "from": "message",
                "strategy": "llm",
                "description": "Nome do serviço, produto, item ou cobrança objeto da contestação.",
            },
            "valor": {
                "from": "message",
                "strategy": "llm",
                "description": "Valor monetário explicitamente informado pelo cliente.",
            },
        },
    )

    schema = runtime._transaction_parameter_schema("tx_tool", {"requires": ["subject", "valor"]})

    assert schema["subject"] == {
        "type": "string",
        "description": "Nome do serviço, produto, item ou cobrança objeto da contestação.",
    }
    assert schema["valor"] == {
        "type": "number",
        "description": "Valor monetário explicitamente informado pelo cliente.",
    }


def test_enriched_args_schema_has_precedence_over_mcp_mapping_description():
    tool = SimpleNamespace(
        args_schema={
            "subject": {"type": "string", "description": "Descrição definida no args_schema."},
            "valor": {"type": "number"},
        },
        requires=["subject", "valor"],
    )
    runtime = _Runtime(
        tool,
        {
            "subject": {"description": "Fallback que não deve sobrescrever."},
            "valor": {"description": "Descrição de fallback para valor."},
        },
    )

    schema = runtime._transaction_parameter_schema("tx_tool", {"requires": ["subject", "valor"]})

    assert schema["subject"]["description"] == "Descrição definida no args_schema."
    assert schema["valor"] == {"type": "number", "description": "Descrição de fallback para valor."}


@pytest.mark.asyncio
async def test_extractor_prompt_uses_optional_semantic_descriptions_and_keeps_null_rule():
    llm = _CaptureLLM()
    extracted = await extract_transaction_parameters(
        llm,
        text="nao contratei TIM CTRL Redes Sociais 8.0",
        tool_name="contestar_cobranca",
        missing_parameters=["subject", "valor"],
        known_arguments={},
        parameter_schema={
            "subject": {
                "type": "string",
                "description": "Nome do serviço, produto, item ou cobrança objeto da contestação.",
            },
            "valor": {
                "type": "number",
                "description": "Valor monetário explicitamente informado pelo cliente.",
            },
        },
        tool_description="Executa contestação de cobrança.",
    )

    assert extracted == {"subject": "TIM CTRL Redes Sociais 8.0"}
    assert "principalmente a descrição semântica quando disponível" in llm.prompt
    assert "A ausência de tipo ou descrição NÃO impede a extração" in llm.prompt
    assert "Em caso de dúvida razoável sobre a correspondência ou o valor, prefira null" in llm.prompt
    assert "Nome do serviço, produto, item ou cobrança objeto da contestação." in llm.prompt
