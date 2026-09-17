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


@pytest.mark.asyncio
async def test_stale_agent_responses_do_not_leak_into_new_turn_projection():
    state = {
        "answer": "Lista atual de serviÃ§os.",
        "route": "vas_agent",
        "active_agent": "vas_agent",
        "intent": "contas_vas_information",
        "agent_responses": [
            {"agent": "contestacao_agent", "answer": "VocÃª confirma Tamboro e Paramount+?", "primary": True, "status": "completed"},
            {"operation_id": "op-2", "agent": "faturas_agent", "answer": "Resposta antiga de fatura.", "primary": False, "status": "completed"},
        ],
        "pending_topics": [],
    }
    result = await drain_pending_topics(state, state["answer"], {})
    assert [r["answer"] for r in result.agent_responses] == ["Lista atual de serviÃ§os."]
    assert result.agent_responses[0]["agent"] == "vas_agent"
    assert result.agent_responses[0]["primary"] is True


@pytest.mark.asyncio
async def test_completed_secondary_result_is_kept_as_durable_operation_result():
    async def billing_agent(state):
        return {
            "answer": "Fatura consultada.",
            "mcp_results": [{"tool_name": "consultar_faturas", "ok": True, "invoice_id": "INV-1"}],
        }
    state = {
        "answer": "Cancelamento concluÃ­do.",
        "route": "contestacao_agent",
        "active_agent": "contestacao_agent",
        "intent": "contas_vas_cancel",
        "operation_results": {
            "op-1": {"operation_id": "op-1", "status": "completed", "answer": "Cancelamento concluÃ­do."}
        },
        "pending_topics": [{
            "operation_id": "op-2", "intent": "contas_invoice_query", "agent": "faturas_agent",
            "domain": "telecom_contas", "tools": ["consultar_faturas"],
            "source_text": "consulte minha fatura", "disposition": "execute", "status": "pending",
        }],
    }
    result = await drain_pending_topics(state, state["answer"], {"faturas_agent": billing_agent})
    assert result.operation_results["op-1"]["answer"] == "Cancelamento concluÃ­do."
    assert result.operation_results["op-2"]["status"] == "completed"
    assert result.operation_results["op-2"]["mcp_results"][0]["invoice_id"] == "INV-1"
    assert [r["answer"] for r in result.agent_responses] == ["Cancelamento concluÃ­do.", "Fatura consultada."]


@pytest.mark.asyncio
async def test_primary_operation_is_not_promoted_while_waiting_confirmation():
    state = {
        "answer": "Você confirma o cancelamento?",
        "route": "contestacao_agent",
        "active_agent": "contestacao_agent",
        "intent": "contas_vas_cancel",
        "transaction_status": "AWAITING_CONFIRMATION",
        "confirmation_required": True,
        "pending_tool_call": {"tool_name": "cancelar_vas_avulso", "arguments": {"subject": "Tamboro"}},
        "multi_intent_plan": {
            "plan_id": "mip-1",
            "operations": [
                {"operation_id": "op-1", "intent": "contas_vas_cancel", "agent": "contestacao_agent", "domain": "telecom_contas", "tools": ["cancelar_vas_avulso"], "source_text": "cancele tamboro"},
            ],
        },
        "operation_results": {},
        "pending_topics": [],
    }
    result = await drain_pending_topics(state, state["answer"], {})
    assert "op-1" not in result.operation_results


@pytest.mark.asyncio
async def test_terminal_primary_operation_is_promoted_and_keeps_previous_results():
    state = {
        "answer": "Tamboro cancelado; Paramount+ não encontrado.",
        "route": "contestacao_agent",
        "active_agent": "contestacao_agent",
        "intent": "state:WAITING_CONTESTACAO_CONFIRMATION",
        "transaction_status": "COMPLETED",
        "multi_intent_plan": {
            "plan_id": "mip-1",
            "operations": [
                {"operation_id": "op-1", "intent": "contas_vas_cancel", "agent": "contestacao_agent", "domain": "telecom_contas", "tools": ["cancelar_vas_avulso"], "source_text": "cancele tamboro e paramount"},
                {"operation_id": "op-2", "intent": "contas_invoice_query", "agent": "faturas_agent", "domain": "telecom_contas", "tools": ["consultar_faturas"], "source_text": "consulte minha fatura"},
            ],
        },
        "operation_results": {
            "op-2": {"operation_id": "op-2", "status": "completed", "answer": "Fatura consultada."}
        },
        "mcp_results": [
            {
                "tool_name": "cancelar_vas_avulso",
                "ok": True,
                "result": {
                    "status": "COMPLETED",
                    "output": {
                        "cancelar_vas_avulso": {
                            "results": [
                                {"subject": "Tamboro Mensal", "success": True, "protocol": "123"},
                                {"subject": "Paramount+", "success": False, "reason": "service_not_found"},
                            ]
                        }
                    },
                },
            }
        ],
        "transaction_evidence": [{"transaction_id": "tx-1", "status": "COMPLETED"}],
        "pending_topics": [],
    }
    result = await drain_pending_topics(state, state["answer"], {})
    assert result.operation_results["op-2"]["answer"] == "Fatura consultada."
    primary = result.operation_results["op-1"]
    assert primary["plan_id"] == "mip-1"
    assert primary["status"] == "completed"
    assert primary["mcp_results"][0]["result"]["output"]["cancelar_vas_avulso"]["results"][1]["reason"] == "service_not_found"
    assert primary["transaction_evidence"][0]["transaction_id"] == "tx-1"
    assert [item["answer"] for item in result.agent_responses] == ["Tamboro cancelado; Paramount+ não encontrado."]

@pytest.mark.asyncio
async def test_persisted_plan_does_not_rehydrate_completed_secondary_topics_on_next_turn():
    calls = {"faturas": 0, "suporte": 0}

    async def billing_agent(state):
        calls["faturas"] += 1
        return {"answer": "Fatura executada novamente - ERRO."}

    async def support_agent(state):
        calls["suporte"] += 1
        return {"answer": "RAG executado novamente - ERRO."}

    plan = {
        "plan_id": "mip-continue-1",
        "operations": [
            {"operation_id": "op-1", "intent": "contas_vas_cancel", "agent": "contestacao_agent", "domain": "telecom_contas", "tools": ["cancelar_vas_avulso"], "source_text": "cancele tamboro"},
            {"operation_id": "op-2", "intent": "contas_invoice_query", "agent": "faturas_agent", "domain": "telecom_contas", "tools": ["consultar_faturas"], "source_text": "consulte minha fatura", "disposition": "execute", "status": "pending"},
            {"operation_id": "op-3", "intent": "contas_knowledge", "agent": "suporte_contas_agent", "domain": "telecom_contas", "tools": [], "source_text": "explique infinity pos", "disposition": "execute", "status": "pending"},
        ],
    }
    state = {
        "answer": "Cancelamento concluído.",
        "route": "contestacao_agent",
        "active_agent": "contestacao_agent",
        "intent": "state:WAITING_CONTESTACAO_CONFIRMATION",
        "transaction_status": "COMPLETED",
        "route_decision": {"route": "contestacao_agent", "intent": "state:WAITING_CONTESTACAO_CONFIRMATION", "metadata": {}},
        "multi_intent_plan": plan,
        # Empty is authoritative: op-2/op-3 were already drained on turn 1.
        "pending_topics": [],
        "operation_results": {
            "op-2": {"operation_id": "op-2", "plan_id": "mip-continue-1", "agent": "faturas_agent", "intent": "contas_invoice_query", "domain": "telecom_contas", "source_text": "consulte minha fatura", "status": "completed", "answer": "Fatura consultada no turno anterior."},
            "op-3": {"operation_id": "op-3", "plan_id": "mip-continue-1", "agent": "suporte_contas_agent", "intent": "contas_knowledge", "domain": "telecom_contas", "source_text": "explique infinity pos", "status": "completed", "answer": "Infinity explicado no turno anterior."},
        },
        "mcp_results": [{"tool_name": "cancelar_vas_avulso", "ok": True, "result": {"status": "COMPLETED"}}],
    }

    result = await drain_pending_topics(
        state,
        state["answer"],
        {"faturas_agent": billing_agent, "suporte_contas_agent": support_agent},
    )

    assert calls == {"faturas": 0, "suporte": 0}
    assert [item["answer"] for item in result.agent_responses] == ["Cancelamento concluído."]
    assert result.operation_results["op-2"]["answer"] == "Fatura consultada no turno anterior."
    assert result.operation_results["op-3"]["answer"] == "Infinity explicado no turno anterior."
    assert result.operation_results["op-1"]["status"] == "completed"


@pytest.mark.asyncio
async def test_completed_queued_topic_is_idempotently_skipped_but_result_remains_available_to_processing():
    calls = 0

    async def billing_agent(state):
        nonlocal calls
        calls += 1
        return {"answer": "não deveria executar"}

    plan = {
        "plan_id": "mip-idempotent-1",
        "operations": [
            {"operation_id": "op-1", "intent": "primary", "agent": "primary_agent", "domain": "test", "tools": [], "source_text": "principal"},
            {"operation_id": "op-2", "intent": "contas_invoice_query", "agent": "faturas_agent", "domain": "telecom_contas", "tools": ["consultar_faturas"], "source_text": "consulte minha fatura", "disposition": "execute", "status": "pending"},
        ],
    }
    existing = {
        "operation_id": "op-2", "plan_id": "mip-idempotent-1", "agent": "faturas_agent",
        "intent": "contas_invoice_query", "domain": "telecom_contas", "source_text": "consulte minha fatura",
        "status": "completed", "answer": "Fatura já consultada.",
        "mcp_results": [{"result": {"invoice_id": "INV-1"}}],
    }
    state = {
        "answer": "Resposta atual.",
        "route": "primary_agent", "active_agent": "primary_agent", "intent": "primary",
        "multi_intent_plan": plan,
        "pending_topics": [dict(plan["operations"][1])],
        "operation_results": {"op-2": existing},
    }

    result = await drain_pending_topics(state, state["answer"], {"faturas_agent": billing_agent})

    assert calls == 0
    assert result.operation_results["op-2"]["mcp_results"][0]["result"]["invoice_id"] == "INV-1"
    assert [item["answer"] for item in result.agent_responses] == ["Resposta atual."]
    assert result.pending_topics == []
