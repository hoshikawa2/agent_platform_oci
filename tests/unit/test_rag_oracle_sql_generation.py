from agent_framework.rag.graph_store import InMemoryGraphStore


def test_inmemory_graph_has_pgql_method_for_interface_parity():
    graph = InMemoryGraphStore()
    assert hasattr(graph, "pgql")
