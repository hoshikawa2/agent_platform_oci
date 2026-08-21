from agent_framework.runtime.agent_runtime import AgentRuntimeMixin


def test_cancel_confirmation_uses_subject_and_never_exposes_internal_vas_label():
    runtime = object.__new__(AgentRuntimeMixin)
    state = {
        "transaction_status": "AWAITING_CONFIRMATION",
        "pending_tool_call": {
            "tool_name": "cancelar_vas_avulso",
            "arguments": {"subject": "TIM Fashion"},
        },
    }

    text = runtime.transaction_confirmation_message(state)

    assert text == (
        "Você confirma o cancelamento do serviço TIM Fashion? "
        "Responda 'sim' para executar ou 'não' para cancelar."
    )
    assert "vas avulso" not in text.lower()
    assert "cancelar_vas_avulso" not in text


def test_existing_retail_confirmation_behavior_is_preserved():
    runtime = object.__new__(AgentRuntimeMixin)
    state = {
        "transaction_status": "AWAITING_CONFIRMATION",
        "pending_tool_call": {
            "tool_name": "solicitar_devolucao",
            "arguments": {"order_id": "123"},
        },
    }

    assert runtime.transaction_confirmation_message(state) == (
        "Você confirma a solicitação de devolução para o pedido 123? "
        "Responda 'sim' para executar ou 'não' para cancelar."
    )
