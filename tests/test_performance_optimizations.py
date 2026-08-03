import asyncio
from types import SimpleNamespace
from agent_framework.runtime.agent_runtime import AgentRuntimeMixin

class Registry:
    def __init__(self):
        self.items={
            'consultar_pedido': SimpleNamespace(selection_keywords=['pedido','status do pedido']),
            'consultar_entrega': SimpleNamespace(selection_keywords=['entrega','rastreio']),
        }
    def get_tool(self,name): return self.items.get(name)

class Router:
    registry=Registry()
    def parameter_extract_rules(self, tool):
        return {'order_id': {'from':'message','type':'string','strategy':'hybrid','pattern':r'(?i)\bpedido\s+([A-Z0-9-]+)\b','group':1}}

class Runtime(AgentRuntimeMixin):
    tool_router=Router()
    llm=None
    settings=SimpleNamespace(SKIP_RAG_WHEN_MCP_SUFFICIENT=True)


def test_selects_only_relevant_read_only_tool():
    r=Runtime()
    assert r._select_read_only_tools(['consultar_pedido','consultar_entrega'],'consultar pedido 123') == ['consultar_pedido']
    assert r._select_read_only_tools(['consultar_pedido','consultar_entrega'],'rastreio da entrega 123') == ['consultar_entrega']


def test_hybrid_regex_does_not_require_llm():
    r=Runtime()
    state={'user_text':'consultar pedido 123','sanitized_input':'consultar pedido 123','context':{},'business_context':{}}
    out=asyncio.run(r._extract_mcp_parameters('consultar_pedido',{},state))
    assert out['order_id']=='123'


def test_direct_answer_is_blocked_for_transactional_request():
    runtime = object.__new__(AgentRuntimeMixin)
    registry = SimpleNamespace(
        tools={"consultar_pedido": object(), "solicitar_devolucao": object()},
        get_tool=lambda name: {
            "consultar_pedido": SimpleNamespace(selection_keywords=["pedido"]),
            "solicitar_devolucao": SimpleNamespace(selection_keywords=["devolver pedido", "devolver", "devolução"]),
        }.get(name),
    )
    runtime.tool_router = SimpleNamespace(registry=registry)
    runtime._resolve_tool_execution_policy = lambda name, args=None: {"operation_type": "transactional" if name == "solicitar_devolucao" else "read_only"}
    state = {"user_text": "Quero devolver o pedido 123"}
    results = [{"ok": True, "tool_name": "consultar_pedido", "result": {"order_id": "123", "status": "ENTREGUE"}}]
    assert runtime.build_direct_mcp_answer(state, results, agent_label="OrdersAgent") is None
