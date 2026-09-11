from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_all_tuning_backend_graphs_support_pending_topics():
    graphs = sorted((ROOT / "Tuning-Performance").glob("**/app/workflows/agent_graph.py"))
    assert graphs
    for path in graphs:
        source = path.read_text(encoding="utf-8")
        assert "from agent_framework.routing.pending_topics import drain_pending_topics" in source, path
        assert '"pending_topics": drained.pending_topics' in source, path
        assert '"handled_topics": drained.handled_topics' in source, path
        assert '"mcp_results": drained.mcp_results' in source, path
        assert '"evidence": drained.mcp_results' in source, path


def test_all_tuning_backend_states_expose_pending_topics():
    states = sorted((ROOT / "Tuning-Performance").glob("**/app/state.py"))
    assert states
    for path in states:
        source = path.read_text(encoding="utf-8")
        assert "pending_topics: list[dict[str, Any]]" in source, path
        assert "handled_topics: list[dict[str, Any]]" in source, path


def test_canonical_templates_delegate_drain_to_framework_helper():
    for template in ("agent_template_backend", "agent_template_backend_day_zero"):
        graph = ROOT / "templates" / template / "app" / "workflows" / "agent_graph.py"
        state = ROOT / "templates" / template / "app" / "state.py"
        graph_source = graph.read_text(encoding="utf-8")
        state_source = state.read_text(encoding="utf-8")
        assert "from agent_framework.routing.pending_topics import drain_pending_topics" in graph_source
        assert "drained = await drain_pending_topics(" in graph_source
        assert '"pending_topics": drained.pending_topics' in graph_source
        assert '"handled_topics": drained.handled_topics' in graph_source
        assert '"mcp_results": drained.mcp_results' in graph_source
        assert '"evidence": drained.mcp_results' in graph_source
        assert "MultiIntentPlanner.public_messages" not in graph_source
        assert "pending_topics: list[dict[str, Any]]" in state_source
        assert "handled_topics: list[dict[str, Any]]" in state_source
