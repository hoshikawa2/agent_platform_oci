import pytest

from agent_framework.routing.pending_topics import drain_pending_topics


@pytest.mark.asyncio
async def test_secondary_topic_does_not_inherit_primary_transaction_state():
    captured = {}

    async def billing_agent(state):
        captured.update(state)
        return {
            "answer": "Aqui está a sua segunda via.",
            "mcp_results": [{"tool_name": "consultar_faturas", "ok": True}],
            "rag": {"provider": "kbdb", "attempted": True, "status": "executed", "document_count": 1},
            "rag_context": "Documento recuperado da base de conhecimento.",
        }

    state = {
        "answer": "Você confirma o cancelamento do Tamboro?",
        "sanitized_input": "quero cancelar Tamboro e quero minha segunda via",
        "confirmation_required": True,
        "active_transaction": {"tool_name": "cancelar_vas_avulso"},
        "transaction_status": "AWAITING_CONFIRMATION",
        "selected_tool_call": {"tool_name": "cancelar_vas_avulso"},
        "pending_tool_call": {"tool_name": "cancelar_vas_avulso"},
        "pending_domain_workflow": {"workflow_name": "cancelamento_vas_avulso"},
        "missing_parameters": ["subject"],
        "next_state": "WAITING_CONTESTACAO_CONFIRMATION",
        "mcp_results": [{"tool_name": "consultar_vas"}],
        "pending_topics": [{
            "operation_id": "op-2",
            "intent": "contas_invoice_query",
            "agent": "faturas_agent",
            "domain": "telecom_contas",
            "tools": ["consultar_faturas"],
            "source_text": "quero minha segunda via",
            "disposition": "execute",
            "status": "pending",
        }],
    }

    result = await drain_pending_topics(
        state, state["answer"], {"faturas_agent": billing_agent}
    )

    assert captured["active_transaction"] is None
    assert captured["selected_tool_call"] == {}
    assert captured["pending_tool_call"] == {}
    assert captured["pending_domain_workflow"] is None
    assert captured["next_state"] is None
    assert captured["sanitized_input"] == "quero minha segunda via"
    assert captured["mcp_results"] == []
    assert captured["mcp_tools"] == ["consultar_faturas"]
    assert captured["available_mcp_tools"] == ["consultar_faturas"]
    assert captured["domain"] == "telecom_contas"
    assert result.answer.startswith("Você confirma o cancelamento")
    assert result.answer.endswith("Aqui está a sua segunda via.")
    assert [item["agent"] for item in result.agent_responses] == ["agent", "faturas_agent"]
    assert result.agent_responses[0]["primary"] is True
    assert result.agent_responses[1]["primary"] is False
    assert result.pending_topics == []
    assert result.mcp_results == [
        {"tool_name": "consultar_vas"},
        {"tool_name": "consultar_faturas", "ok": True},
    ]
    assert result.rag_results[0]["metadata"]["provider"] == "kbdb"
    assert result.rag_results[0]["context"] == "Documento recuperado da base de conhecimento."


@pytest.mark.asyncio
async def test_deferred_transaction_is_promoted_after_primary_completes():
    async def cancellation_agent(state):
        assert state["user_text"] == "quero cancelar meu pedido"
        return {
            "answer": "Você confirma o cancelamento do pedido PED-1001?",
            "transaction_status": "AWAITING_CONFIRMATION",
            "confirmation_required": True,
            "pending_tool_call": {
                "tool_name": "cancelar_pedido",
                "arguments": {"order_id": "PED-1001"},
            },
            "active_transaction": {
                "tool_name": "cancelar_pedido",
                "status": "AWAITING_CONFIRMATION",
            },
        }

    state = {
        "answer": "A devolução foi registrada com sucesso.",
        "route": "support_agent",
        "active_agent": "support_agent",
        "intent": "retail_support_exchange_return",
        "transaction_status": "COMPLETED",
        "pending_topics": [{
            "operation_id": "op-3",
            "intent": "retail_order_cancel",
            "agent": "orders_agent",
            "domain": "retail",
            "tools": ["consultar_pedido", "cancelar_pedido"],
            "source_text": "quero cancelar meu pedido",
            "disposition": "defer",
            "status": "pending",
        }],
    }

    result = await drain_pending_topics(
        state, state["answer"], {"orders_agent": cancellation_agent}
    )

    assert result.pending_topics == []
    assert result.state_patch["route"] == "orders_agent"
    assert result.state_patch["intent"] == "retail_order_cancel"
    assert result.state_patch["transaction_status"] == "AWAITING_CONFIRMATION"
    assert result.state_patch["pending_tool_call"]["tool_name"] == "cancelar_pedido"
    assert result.agent_responses[-1]["primary"] is True
    assert result.agent_responses[-1]["agent"] == "orders_agent"
