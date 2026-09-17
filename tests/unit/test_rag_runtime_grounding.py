from types import SimpleNamespace

import pytest

from agent_framework.rag.rag_service import RagResult
from agent_framework.rag.vector_store import VectorDocument
from agent_framework.runtime.agent_runtime import AgentRuntimeMixin


class DummyRag:
    def __init__(self):
        self.calls = []

    async def retrieve(self, query, *, namespace="default", graph_node=None, rewrite=False, k=None):
        self.calls.append((query, namespace, graph_node, rewrite))
        return RagResult(
            query=query,
            documents=[VectorDocument(id="kb-1", content="Tarifação documentada", metadata={}, score=0.9)],
            graph_neighbors=[],
            latency_ms=3,
            metadata={"provider": "kbdb", "confidence": "high", "low_confidence": False},
        )


class Runtime(AgentRuntimeMixin):
    pass


def _runtime(**settings):
    rt = Runtime()
    base = dict(
        RAG_PROVIDER="kbdb",
        SKIP_RAG_WHEN_MCP_SUFFICIENT=True,
        ENABLE_RAG_QUERY_REWRITE=False,
        ENABLE_RAG_CONTEXT_COMPRESSION=False,
        RAG_GROUNDED_ONLY=False,
        KBDB_GROUNDED_ONLY=True,
        LONG_TERM_MEMORY_INJECT_CONTEXT=False,
    )
    base.update(settings)
    rt.settings = SimpleNamespace(**base)
    rt.rag_service = DummyRag()
    rt.guardrail_pipeline = None
    return rt


@pytest.mark.asyncio
async def test_successful_mcp_does_not_skip_rag_without_explicit_sufficiency():
    rt = _runtime()
    state = {
        "agent_id": "telecom_contas",
        "user_text": "Como funciona a tarifação do plano Infinity Pós?",
        "sanitized_input": "Como funciona a tarifação do plano Infinity Pós?",
        "mcp_results": [{"ok": True, "tool_name": "qualquer_tool", "result": {"plano": "Controle 50GB"}}],
    }

    context, metadata = await rt._retrieve_rag_context(state)

    assert rt.rag_service.calls
    assert "Tarifação documentada" in context
    assert metadata["provider"] == "kbdb"
    assert metadata["status"] == "executed"
    assert metadata["document_count"] == 1


@pytest.mark.asyncio
async def test_rag_skips_only_when_mcp_explicitly_declares_sufficiency():
    rt = _runtime()
    state = {
        "agent_id": "telecom_contas",
        "user_text": "qual é meu plano?",
        "sanitized_input": "qual é meu plano?",
        "mcp_results": [{"ok": True, "result": {"plano": "Controle 50GB", "rag_sufficient": True}}],
    }

    context, metadata = await rt._retrieve_rag_context(state)

    assert context == ""
    assert not rt.rag_service.calls
    assert metadata["reason"] == "mcp_explicitly_sufficient"


def test_kbdb_build_messages_injects_grounding_policy():
    rt = _runtime()
    state = {
        "user_text": "Como funciona?",
        "sanitized_input": "Como funciona?",
        "context": {},
        "business_context": {},
    }
    messages = rt.build_messages(
        state,
        system_prompt="system",
        mcp_results=[{"ok": True, "result": {"plano": "Controle"}}],
        rag_context="",
        rag_metadata={"provider": "kbdb", "enabled": True, "status": "empty", "document_count": 0},
    )
    user = next(m["content"] for m in messages if m["role"] == "user")
    assert "Política de grounding obrigatória" in user
    assert "Não complete lacunas usando conhecimento paramétrico" in user

@pytest.mark.asyncio
@pytest.mark.parametrize("workflow_status", ["COMPLETED", "FAILED"])
async def test_rag_skips_when_all_turn_workflows_are_terminal(workflow_status):
    rt = _runtime()
    state = {
        "agent_id": "telecom_contas",
        "user_text": "sim",
        "sanitized_input": "sim",
        "mcp_results": [
            {
                "ok": True,
                "tool_name": "cancelar_vas_avulso",
                "result": {
                    "execution_id": "wf-1",
                    "workflow_name": "cancelamento_vas_avulso",
                    "status": workflow_status,
                    "output": {"answer": "resultado operacional"},
                },
                "metadata": {
                    "workflow_name": "cancelamento_vas_avulso",
                    "workflow_status": workflow_status,
                },
            }
        ],
    }

    context, metadata = await rt._retrieve_rag_context(state)

    assert context == ""
    assert not rt.rag_service.calls
    assert metadata["status"] == "skipped"
    assert metadata["reason"] == "all_turn_workflows_terminal"
    assert metadata["workflow_statuses"] == [workflow_status]


@pytest.mark.asyncio
async def test_rag_still_runs_when_any_turn_workflow_is_not_terminal():
    rt = _runtime()
    state = {
        "agent_id": "telecom_contas",
        "user_text": "sim",
        "sanitized_input": "sim",
        "mcp_results": [
            {
                "ok": True,
                "result": {"execution_id": "wf-1", "workflow_name": "w1", "status": "COMPLETED"},
                "metadata": {"workflow_status": "COMPLETED"},
            },
            {
                "ok": True,
                "result": {"execution_id": "wf-2", "workflow_name": "w2", "status": "RUNNING"},
                "metadata": {"workflow_status": "RUNNING"},
            },
        ],
    }

    context, metadata = await rt._retrieve_rag_context(state)

    assert rt.rag_service.calls
    assert "Tarifação documentada" in context
    assert metadata["status"] == "executed"


@pytest.mark.asyncio
async def test_explicit_requires_rag_overrides_terminal_workflow_skip():
    rt = _runtime()
    state = {
        "agent_id": "telecom_contas",
        "user_text": "sim",
        "sanitized_input": "sim",
        "mcp_results": [
            {
                "ok": True,
                "result": {
                    "execution_id": "wf-1",
                    "workflow_name": "w1",
                    "status": "COMPLETED",
                    "requires_rag": True,
                    "rag_query": "explicar regra de negócio",
                },
                "metadata": {"workflow_status": "COMPLETED"},
            }
        ],
    }

    context, metadata = await rt._retrieve_rag_context(state)

    assert rt.rag_service.calls
    assert rt.rag_service.calls[0][0] == "explicar regra de negócio"
    assert "Tarifação documentada" in context
    assert metadata["required_by_tool"] is True


@pytest.mark.asyncio
async def test_terminal_workflow_does_not_skip_rag_when_operation_is_pending():
    rt = _runtime()
    state = {
        "agent_id": "telecom_contas",
        "user_text": "sim",
        "sanitized_input": "sim",
        "pending_topics": [
            {"operation_id": "op-2", "intent": "invoice_query", "status": "pending"}
        ],
        "operation_results": {},
        "mcp_results": [
            {
                "ok": True,
                "result": {"execution_id": "wf-1", "workflow_name": "w1", "status": "COMPLETED"},
                "metadata": {"workflow_status": "COMPLETED"},
            }
        ],
    }

    context, metadata = await rt._retrieve_rag_context(state)

    assert rt.rag_service.calls
    assert "Tarifação documentada" in context
    assert metadata["status"] == "executed"


@pytest.mark.asyncio
async def test_terminal_workflow_does_not_skip_rag_when_knowledge_operation_is_unresolved():
    rt = _runtime()
    state = {
        "agent_id": "telecom_contas",
        "user_text": "sim",
        "sanitized_input": "sim",
        "multi_intent_plan": {
            "plan_id": "mip-1",
            "operations": [
                {"operation_id": "op-1", "intent": "cancel", "status": "completed"},
                {"operation_id": "op-2", "intent": "account_knowledge", "status": "pending"},
            ],
        },
        # op-1 está resolvida, op-2 ainda não possui resultado terminal.
        "operation_results": {"op-1": {"status": "completed"}},
        "mcp_results": [
            {
                "ok": True,
                "result": {"execution_id": "wf-1", "workflow_name": "w1", "status": "COMPLETED"},
                "metadata": {"workflow_status": "COMPLETED"},
            }
        ],
    }

    context, metadata = await rt._retrieve_rag_context(state)

    assert rt.rag_service.calls
    assert "Tarifação documentada" in context
    assert metadata["status"] == "executed"


@pytest.mark.asyncio
async def test_completed_operation_results_prevent_stale_plan_from_counting_as_pending():
    rt = _runtime()
    state = {
        "agent_id": "telecom_contas",
        "user_text": "sim",
        "sanitized_input": "sim",
        "multi_intent_plan": {
            "plan_id": "mip-1",
            "operations": [
                {"operation_id": "op-1", "intent": "cancel", "status": "pending"},
                {"operation_id": "op-2", "intent": "invoice_query", "status": "pending"},
                {"operation_id": "op-3", "intent": "account_knowledge", "status": "pending"},
            ],
        },
        "operation_results": {
            "op-1": {"status": "completed"},
            "op-2": {"status": "completed"},
            "op-3": {"status": "completed"},
        },
        "mcp_results": [
            {
                "ok": True,
                "result": {"execution_id": "wf-1", "workflow_name": "w1", "status": "COMPLETED"},
                "metadata": {"workflow_status": "COMPLETED"},
            }
        ],
    }

    context, metadata = await rt._retrieve_rag_context(state)

    assert context == ""
    assert not rt.rag_service.calls
    assert metadata["status"] == "skipped"
    assert metadata["reason"] == "all_turn_workflows_terminal"
