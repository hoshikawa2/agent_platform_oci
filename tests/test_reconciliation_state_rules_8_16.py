import json
import pytest
from types import SimpleNamespace

from agent_framework.runtime.agent_runtime import AgentRuntimeMixin


class _Router:
    def __init__(self):
        self.registry = SimpleNamespace(
            tools={"contestar_cobranca": object(), "validar_contestacao": object()},
            get_tool=lambda name: SimpleNamespace(
                description="Contesta uma cobrança após validação",
                args_schema={
                    "subject": {
                        "type": "string",
                        "description": "Referência a um item concreto e identificável da fatura",
                        "user_prompt": "Qual cobrança ou item você deseja contestar?",
                    },
                    "valor": {
                        "type": "number",
                        "description": "Valor monetário explicitamente associado pelo cliente ao item",
                        "user_prompt": "Qual é o valor da cobrança que você deseja contestar?",
                    },
                },
                requires=["subject", "valor"],
            ) if name == "contestar_cobranca" else None,
        )

    def resolve_execution_policy(self, tool_name, arguments=None):
        if tool_name == "contestar_cobranca":
            return {
                "operation_type": "transactional",
                "require_confirmation": True,
                "requires": ["subject", "valor"],
                "policy_source": "test",
                "pre_validation": {"enabled": True, "tool": "validar_contestacao", "fail_open": False},
            }
        return {"operation_type": "read_only", "require_confirmation": False, "policy_source": "test"}


class _LLM:
    async def ainvoke(self, messages, **kwargs):
        prompt = messages[-1]["content"]
        generation = kwargs.get("generation_name")
        if generation == "llm.transaction_parameter_current_only":
            low = prompt.lower()
            fields = json.loads(prompt.split("Formato: ", 1)[1])
            out = dict(fields)
            if "quatorze e noventa e nove" in low:
                if "valor" in out:
                    out["valor"] = 14.99
            elif "vinte e cinco e cinquenta" in low:
                if "valor" in out:
                    out["valor"] = 25.50
            elif "dezenove e noventa e nove" in low:
                if "valor" in out:
                    out["valor"] = 19.99
            return {"content": json.dumps(out, ensure_ascii=False)}
        if generation == "llm.transaction_parameter_extraction":
            # Deliberately leave subject unresolved so scenario 8 exercises the
            # unique anchored structural candidate + authoritative validator path.
            return {"content": json.dumps({"fields": {
                "subject": {"decision": "unresolved", "value": None, "source": ""},
                "valor": {"decision": "preserve", "value": None, "source": "state"},
            }}, ensure_ascii=False)}
        return {"content": "{}"}


class _Runtime(AgentRuntimeMixin):
    def __init__(self):
        self.tool_router = _Router()
        self.llm = _LLM()
        self.calls = []

    async def _call_mcp_tool(self, tool_name, arguments, state):
        self.calls.append((tool_name, dict(arguments)))
        if tool_name != "validar_contestacao":
            return {"ok": True, "tool_name": tool_name, "result": {"status": "OK"}}

        subject = str(arguments.get("subject") or "")
        valor = arguments.get("valor")
        # Canonicalize the raw anchored fragment from scenario 8.
        if "Tamboro Mensal" in subject:
            canonical = "Tamboro Mensal"
        else:
            return {"ok": True, "eligible": False, "status": "NEEDS_PARAMETER", "parameter": "subject"}

        if float(valor) not in {14.99, 19.99}:
            return {
                "ok": True,
                "eligible": False,
                "status": "NEEDS_PARAMETER",
                "parameter": "valor",
                "clear_fields": ["resolved_value"],
            }
        return {
            "ok": True,
            "eligible": True,
            "transaction_decision": {
                "resolved_arguments": {"subject": canonical, "valor": float(valor)}
            },
        }


def _collecting_state(arguments, text, *, metadata=None, context=None):
    return {
        "user_text": text,
        "sanitized_input": text,
        "route": "contestacao_agent",
        "intent": "state:COLLECTING_CONTESTACAO_PARAMETERS",
        "transaction_status": "COLLECTING_PARAMETERS",
        "active_transaction": {
            "transaction_id": "tx",
            "tool_name": "contestar_cobranca",
            "arguments": dict(arguments),
            "status": "COLLECTING_PARAMETERS",
            "parameter_schema": {
                "subject": {"type": "string", "description": "Referência a um item concreto e identificável da fatura"},
                "valor": {"type": "number", "description": "Valor monetário explicitamente associado pelo cliente ao item"},
            },
            "parameter_conversational_context": context or "",
        },
        "selected_tool_call": {"tool_name": "contestar_cobranca", "arguments": dict(arguments)},
        "missing_parameters": [x for x in ["subject", "valor"] if arguments.get(x) in (None, "")],
        "route_decision": {"metadata": metadata or {}},
    }


@pytest.mark.asyncio
async def test_scenario8_value_anchor_reconciles_subject_then_awaits_confirmation():
    runtime = _Runtime()
    context = (
        "user: tem uma cobrança aqui que eu não reconheço\n"
        "assistant: Analisando a fatura. * Cobrança Tamboro Mensal no valor de R$ 14.99 no dia 01/11/25. "
        "* Cobrança TIM Fashion Mensal no valor de R$ 10.00 no dia 01/11/25."
    )
    state = _collecting_state(
        {},
        "é a de quatorze e noventa e nove",
        metadata={
            "contextual_reentry": True,
            "original_input": "é a de quatorze e noventa e nove",
            "relevant_conversation_context": context,
        },
        context=context,
    )

    result = await runtime.execute_tools_for_intent(state, tools=[])

    assert state["transaction_status"] == "AWAITING_CONFIRMATION"
    assert state["missing_parameters"] == []
    assert state["pending_tool_call"]["arguments"]["subject"] == "Tamboro Mensal"
    assert state["pending_tool_call"]["arguments"]["valor"] == 14.99
    assert state["transaction_pre_validation"]["eligible"] is True
    assert result[-1]["awaiting_confirmation"] is True


@pytest.mark.asyncio
async def test_scenario16_invalid_value_clears_only_value_and_preserves_subject():
    runtime = _Runtime()
    state = _collecting_state({"subject": "Tamboro Mensal"}, "é a de vinte e cinco e cinquenta")

    result = await runtime.execute_tools_for_intent(state, tools=[])

    assert state["transaction_status"] == "COLLECTING_PARAMETERS"
    assert state["active_transaction"]["arguments"]["subject"] == "Tamboro Mensal"
    assert "valor" not in state["active_transaction"]["arguments"]
    assert state["missing_parameters"] == ["valor"]
    assert result[-1]["collecting_parameters"] is True


@pytest.mark.asyncio
async def test_scenario16_current_turn_correction_updates_existing_value_then_awaits_confirmation():
    runtime = _Runtime()
    state = _collecting_state(
        {"subject": "Tamboro Mensal", "valor": 25.50},
        "desculpa é a de dezenove e noventa e nove",
    )
    # The old value exists, so missing_parameters alone must NOT restrict which
    # current-turn fields may be corrected.
    state["missing_parameters"] = ["subject"]

    result = await runtime.execute_tools_for_intent(state, tools=[])

    assert state["transaction_status"] == "AWAITING_CONFIRMATION"
    assert state["missing_parameters"] == []
    assert state["pending_tool_call"]["arguments"]["subject"] == "Tamboro Mensal"
    assert state["pending_tool_call"]["arguments"]["valor"] == 19.99
    assert state["transaction_pre_validation"]["eligible"] is True
    assert result[-1]["awaiting_confirmation"] is True
