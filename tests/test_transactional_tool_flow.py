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


class _TransactionTestLLM:
    async def ainvoke(self, messages, **kwargs):
        import json
        prompt = messages[-1]["content"]
        if kwargs.get("profile_name") == "transaction_parameter_extraction" or "pending_parameters:" in prompt:
            pending = json.loads(prompt.split("pending_parameters: ", 1)[1].split("\n", 1)[0])
            user = prompt.split("user_message: ", 1)[1].split("\nFormato obrigatório:", 1)[0].strip()
            out = {name: None for name in pending}
            low = user.lower()
            if "order_id" in out:
                import re
                m = re.search(r"\b(?:ped[- ]?)?(\d+)\b", low, re.I)
                if m:
                    out["order_id"] = ("PED-" + m.group(1)) if "ped" in m.group(0).lower() else m.group(1)
            if "reason" in out and ("arrepend" in low or "desisti" in low):
                out["reason"] = "Arrependimento da compra" if "arrepend" in low else "desisti da compra"
            return {"content": json.dumps(out, ensure_ascii=False)}
        return {"content": "{}"}


class _PolicyRouter:
    def __init__(self):
        from types import SimpleNamespace
        self.registry = SimpleNamespace(
            tools={"consultar_pedido": object(), "solicitar_devolucao": object()},
            get_tool=lambda name: {
                "consultar_pedido": SimpleNamespace(selection_keywords=["consultar pedido", "pedido"], args_schema={}, requires=[]),
                "solicitar_devolucao": SimpleNamespace(
                    selection_keywords=["devolver pedido", "devolver", "devolução", "arrependimento"],
                    args_schema={"order_id": "string", "reason": "string"},
                    requires=["order_id", "reason"],
                    description="Solicita devolução de pedido",
                ),
            }.get(name),
        )

    def resolve_execution_policy(self, tool_name, arguments=None):
        if tool_name == "solicitar_devolucao":
            return {"operation_type": "transactional", "require_confirmation": True, "requires": ["order_id", "reason"], "policy_source": "test"}
        return {"operation_type": "read_only", "require_confirmation": False, "policy_source": "test"}

    def validate_execution_policy(self, tool_name, arguments=None):
        policy = self.resolve_execution_policy(tool_name, arguments)
        if policy["require_confirmation"] and not (arguments or {}).get("confirmed"):
            return False, "Tool exige confirmação explícita antes da execução", policy
        return True, None, policy


class _Runtime(AgentRuntimeMixin):
    def __init__(self):
        self.tool_router = _PolicyRouter()
        self.llm = _TransactionTestLLM()
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
        import json
        prompt = messages[-1]["content"]
        if kwargs.get("profile_name") == "transaction_parameter_extraction":
            pending = json.loads(prompt.split("pending_parameters: ", 1)[1].split("\n", 1)[0])
            out = {name: None for name in pending}
            if "subject" in out:
                out["subject"] = "TIM CTRL Redes Sociais 8.0"
            return {"content": json.dumps(out, ensure_ascii=False)}
        if kwargs.get("profile_name") == "mcp_parameter_extraction":
            if "Campo: motivo" in prompt:
                return {"content": '{"motivo": "não contratei"}'}
            if "Campo: valor" in prompt:
                return {"content": '{"valor": null}'}
        return {"content": "{}"}


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

class _EvidenceRuntime(_Runtime):
    async def _call_mcp_tool(self, tool_name, arguments, state):
        self.calls.append((tool_name, dict(arguments)))
        if tool_name == "solicitar_devolucao":
            return {
                "ok": True,
                "tool_name": tool_name,
                "result": {
                    "order_id": arguments.get("order_id"),
                    "status": "PROCESSANDO",
                    "protocolo": "DEV-2026-001",
                },
            }
        return {
            "ok": True,
            "tool_name": tool_name,
            "result": {
                "order_id": arguments.get("order_id") or "123",
                "status": "EM_TRANSPORTE",
            },
        }


@pytest.mark.asyncio
async def test_completed_transaction_becomes_reusable_operational_evidence():
    runtime = _EvidenceRuntime()
    state = {
        "user_text": "Quero devolver o pedido 123 porque me arrependi",
        "sanitized_input": "Quero devolver o pedido 123 porque me arrependi",
        "mcp_tools": ["consultar_pedido", "solicitar_devolucao"],
        "route": "support_agent",
        "intent": "retail_support_exchange_return",
    }

    await runtime.execute_tools_for_intent(state)
    state["user_text"] = "sim"
    state["sanitized_input"] = "sim"
    await runtime.execute_tools_for_intent(state)

    assert state["transaction_status"] == "COMPLETED"
    assert state["last_transaction"]["result"]["result"]["protocolo"] == "DEV-2026-001"
    assert state["transaction_evidence"][-1]["tool_name"] == "solicitar_devolucao"
    assert state["transaction_evidence"][-1]["result"]["result"]["protocolo"] == "DEV-2026-001"

    # New read-only turn on the same resource must receive the prior transaction
    # as grounded operational evidence, without reactivating the transaction.
    state["user_text"] = "quero meu pedido 123"
    state["sanitized_input"] = state["user_text"]
    state["mcp_tools"] = ["consultar_pedido"]
    state["intent"] = "retail_order_tracking"
    results = await runtime._collect_mcp_context(state)

    assert results[0]["result"]["order_id"] == "123"
    assert state["active_transaction"] is None
    relevant = state["relevant_transaction_evidence"]
    assert len(relevant) == 1
    assert relevant[0]["result"]["result"]["protocolo"] == "DEV-2026-001"

    messages = runtime.build_messages(
        state,
        system_prompt="Use apenas evidências fornecidas pelo framework.",
        mcp_results=results,
    )
    rendered = "\n".join(message["content"] for message in messages)
    assert "Evidências operacionais de transações anteriores" in rendered
    assert "DEV-2026-001" in rendered


def test_transaction_evidence_is_correlated_by_resource_identifier():
    runtime = _EvidenceRuntime()
    state = {
        "transaction_evidence": [
            {
                "transaction_id": "tx-123",
                "tool_name": "solicitar_devolucao",
                "arguments": {"order_id": "123"},
                "status": "COMPLETED",
                "result": {"result": {"order_id": "123", "protocolo": "DEV-123"}},
            },
            {
                "transaction_id": "tx-999",
                "tool_name": "solicitar_devolucao",
                "arguments": {"order_id": "999"},
                "status": "COMPLETED",
                "result": {"result": {"order_id": "999", "protocolo": "DEV-999"}},
            },
        ]
    }
    current = [{"ok": True, "tool_name": "consultar_pedido", "result": {"order_id": "123"}}]
    relevant = runtime.transaction_evidence_for_turn(state, current)
    assert [item["transaction_id"] for item in relevant] == ["tx-123"]


def test_tool_policy_registry_reads_pre_validation(tmp_path: Path):
    config = tmp_path / "tool_policies.yaml"
    config.write_text("""version: 1
defaults:
  operation_type: read_only
  require_confirmation: false
tool_policies:
  contestar_cobranca:
    operation_type: transactional
    require_confirmation: true
    requires: [subject, valor]
    pre_validation:
      enabled: true
      tool: validar_contestacao
      fail_open: false
""", encoding="utf-8")
    policy = ToolPolicyRegistry(str(config)).get("contestar_cobranca")
    assert policy is not None
    assert policy.pre_validation.enabled is True
    assert policy.pre_validation.tool == "validar_contestacao"
    assert policy.pre_validation.fail_open is False


class _PreValidationRouter(_ContestPolicyRouter):
    def __init__(self):
        super().__init__()
        from types import SimpleNamespace
        self.registry = SimpleNamespace(
            tools={"contestar_cobranca": object(), "validar_contestacao": object()},
            get_tool=lambda name: SimpleNamespace(
                selection_keywords=["contestar", "não contratei", "nao contratei"] if name == "contestar_cobranca" else []
            ),
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
        return {"operation_type": "internal", "require_confirmation": False, "requires": [], "policy_source": "test", "pre_validation": {"enabled": False}}


class _PreValidationRuntime(AgentRuntimeMixin):
    def __init__(self, eligible: bool):
        self.tool_router = _PreValidationRouter()
        self.calls = []
        self.eligible = eligible

    async def _call_mcp_tool(self, tool_name, arguments, state):
        self.calls.append((tool_name, dict(arguments)))
        if tool_name == "validar_contestacao":
            payload = ({"eligible": True, "status": "ELIGIBLE"} if self.eligible else {
                "eligible": False,
                "status": "OUT_OF_SCOPE",
                "category": "plano",
                "error": "item não elegível para contestação",
            })
            return {"ok": True, "tool_name": tool_name, "result": payload}
        return {"ok": True, "tool_name": tool_name, "result": {"status": "OPENED"}}


@pytest.mark.asyncio
async def test_pre_validation_rejects_before_confirmation_without_executing_transaction():
    runtime = _PreValidationRuntime(eligible=False)
    state = {
        "user_text": "quero contestar TIM CTRL no valor de R$ 71,99",
        "sanitized_input": "quero contestar TIM CTRL no valor de R$ 71,99",
        "mcp_tools": ["contestar_cobranca"],
        "route": "contestacao_agent",
        "intent": "contas_contestation",
        "context": {"tool_arguments": {"subject": "TIM CTRL Redes Sociais 8.0", "valor": 71.99}},
    }
    result = await runtime.execute_tools_for_intent(state)
    assert [name for name, _ in runtime.calls] == ["validar_contestacao"]
    assert result[-1]["pre_validation"] is True
    assert result[-1]["transaction_status"] == "OUT_OF_SCOPE"
    assert state["transaction_status"] == "OUT_OF_SCOPE"
    assert state.get("pending_tool_call") in ({}, None)
    assert state["confirmation_required"] is False


@pytest.mark.asyncio
async def test_pre_validation_passes_then_waits_for_confirmation():
    runtime = _PreValidationRuntime(eligible=True)
    state = {
        "user_text": "quero contestar serviço X no valor de R$ 10,00",
        "sanitized_input": "quero contestar serviço X no valor de R$ 10,00",
        "mcp_tools": ["contestar_cobranca"],
        "route": "contestacao_agent",
        "intent": "contas_contestation",
        "context": {"tool_arguments": {"subject": "serviço X", "valor": 10.0}},
    }
    result = await runtime.execute_tools_for_intent(state)
    assert [name for name, _ in runtime.calls] == ["validar_contestacao"]
    assert result[-1]["awaiting_confirmation"] is True
    assert state["transaction_status"] == "AWAITING_CONFIRMATION"
    assert state["pending_tool_call"]["tool_name"] == "contestar_cobranca"

@pytest.mark.asyncio
async def test_pre_validation_runs_after_last_required_parameter_before_confirmation():
    runtime = _PreValidationRuntime(eligible=False)
    state = {
        "user_text": "R$ 71,99",
        "sanitized_input": "R$ 71,99",
        "route": "contestacao_agent",
        "intent": "state:COLLECTING_CONTESTACAO_PARAMETERS",
        "transaction_status": "COLLECTING_PARAMETERS",
        "selected_tool_call": {
            "tool_name": "contestar_cobranca",
            "arguments": {"subject": "TIM CTRL Redes Sociais 8.0", "motivo": "não contratei"},
        },
        "context": {"tool_arguments": {"valor": 71.99}},
    }
    result = await runtime.execute_tools_for_intent(state, tools=[])
    assert [name for name, _ in runtime.calls] == ["validar_contestacao"]
    assert runtime.calls[0][1]["subject"] == "TIM CTRL Redes Sociais 8.0"
    assert runtime.calls[0][1]["valor"] == 71.99
    assert result[-1]["pre_validation"] is True
    assert state["transaction_status"] == "OUT_OF_SCOPE"
    assert state["confirmation_required"] is False
    assert not state.get("pending_tool_call")


def test_transaction_state_patch_exposes_prevalidation_and_terminal_lifecycle():
    runtime = _PreValidationRuntime(eligible=False)
    state = {
        "transaction_status": "OUT_OF_SCOPE",
        "next_state": None,
        "selected_tool_call": {},
        "pending_tool_call": {},
        "confirmation_required": False,
        "confirmation_received": False,
        "transaction_pre_validation": {
            "tool_name": "contestar_cobranca",
            "validator_tool": "validar_contestacao",
            "eligible": False,
            "status": "OUT_OF_SCOPE",
            "terminal": True,
        },
    }
    patch = runtime.transaction_state_patch(state)
    assert patch["transaction_pre_validation"]["eligible"] is False
    assert patch["transaction_pre_validation"]["status"] == "OUT_OF_SCOPE"
    assert patch["next_state"] is None
    assert patch["transaction_status"] == "OUT_OF_SCOPE"
    assert patch["confirmation_required"] is False


@pytest.mark.asyncio
async def test_pre_validation_rejection_clears_collecting_latches_and_is_exposed_in_patch():
    runtime = _PreValidationRuntime(eligible=False)
    state = {
        "user_text": "R$ 71,99",
        "sanitized_input": "R$ 71,99",
        "route": "contestacao_agent",
        "intent": "state:COLLECTING_CONTESTACAO_PARAMETERS",
        "next_state": "COLLECTING_CONTESTACAO_PARAMETERS",
        "transaction_status": "COLLECTING_PARAMETERS",
        "selected_tool_call": {
            "tool_name": "contestar_cobranca",
            "arguments": {"subject": "TIM CTRL Redes Sociais 8.0", "motivo": "não contratei"},
        },
        "pending_tool_call": {},
        "missing_parameters": ["valor"],
        "confirmation_required": False,
        "context": {"tool_arguments": {"valor": 71.99}},
    }
    result = await runtime.execute_tools_for_intent(state, tools=[])
    assert result[-1]["pre_validation"] is True
    assert state["transaction_status"] == "OUT_OF_SCOPE"
    assert state["next_state"] is None
    assert state["active_transaction"] is None
    assert state["selected_tool_call"] == {}
    assert state["pending_tool_call"] == {}
    assert state["missing_parameters"] == []
    assert state["confirmation_required"] is False
    assert state["confirmation_received"] is False
    assert state["transaction_pre_validation"]["eligible"] is False
    assert state["transaction_pre_validation"]["status"] == "OUT_OF_SCOPE"
    assert state["transaction_pre_validation"]["terminal"] is True
    patch = runtime.transaction_state_patch(state)
    assert patch["transaction_pre_validation"] == state["transaction_pre_validation"]
    assert patch["next_state"] is None
@pytest.mark.asyncio
async def test_collecting_parameters_can_be_cancelled_explicitly():
    runtime = _ContestRuntime()
    state = {
        "user_text": "nova intenção classificada pelo router",
        "sanitized_input": "nova intenção classificada pelo router",
        "route": "contestacao_agent",
        "intent": "state:COLLECTING_CONTESTACAO_PARAMETERS",
        "transaction_status": "COLLECTING_PARAMETERS",
        "active_transaction": {
            "transaction_id": "tx-1",
            "tool_name": "contestar_cobranca",
            "arguments": {},
            "status": "COLLECTING_PARAMETERS",
            "started_from_intent": "contas_contestation",
        },
        "selected_tool_call": {"tool_name": "contestar_cobranca", "arguments": {}},
        "missing_parameters": ["subject"],
        "next_state": "COLLECTING_CONTESTACAO_PARAMETERS",
        "route_decision": {"metadata": {"transaction_interruption": "intent_shift"}},
    }

    result = await runtime.execute_tools_for_intent(state, tools=[])

    assert result == []
    assert state["transaction_status"] == "CANCELLED"
    assert state["active_transaction"] is None
    assert state["next_state"] is None
    assert state["missing_parameters"] == []


@pytest.mark.asyncio
async def test_route_intent_shift_clears_collecting_transaction_before_new_tools():
    runtime = _ContestRuntime()
    state = {
        "user_text": "quais são meus serviços?",
        "sanitized_input": "quais são meus serviços?",
        "route": "vas_agent",
        "intent": "contas_vas_information",
        "route_decision": {
            "route": "vas_agent",
            "agent": "vas_agent",
            "intent": "contas_vas_information",
            "metadata": {"transaction_interruption": "intent_shift"},
        },
        "transaction_status": "COLLECTING_PARAMETERS",
        "active_transaction": {
            "transaction_id": "tx-2",
            "tool_name": "contestar_cobranca",
            "arguments": {},
            "status": "COLLECTING_PARAMETERS",
            "started_from_intent": "contas_contestation",
        },
        "selected_tool_call": {"tool_name": "contestar_cobranca", "arguments": {}},
        "missing_parameters": ["subject"],
        "next_state": "COLLECTING_CONTESTACAO_PARAMETERS",
    }

    result = await runtime.execute_tools_for_intent(state, tools=[])

    assert result == []
    assert state["transaction_status"] == "CANCELLED"
    assert state["active_transaction"] is None
    assert state["next_state"] is None
    assert state["missing_parameters"] == []
    assert state["tool_policy_result"]["action"] == "cancelled_by_intent_shift"
