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
        assert '"rag_results": drained.rag_results' in source, path
        assert 'list(drained.mcp_results) + list(drained.rag_results)' in source, path


def test_all_tuning_backend_states_expose_pending_topics():
    states = sorted((ROOT / "Tuning-Performance").glob("**/app/state.py"))
    assert states
    for path in states:
        source = path.read_text(encoding="utf-8")
        assert "pending_topics: list[dict[str, Any]]" in source, path
        assert "handled_topics: list[dict[str, Any]]" in source, path
        assert "rag_results: list[dict[str, Any]]" in source, path


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
        assert '"rag_results": drained.rag_results' in graph_source
        assert 'list(drained.mcp_results) + list(drained.rag_results)' in graph_source
        assert "MultiIntentPlanner.public_messages" not in graph_source
        assert "pending_topics: list[dict[str, Any]]" in state_source
        assert "handled_topics: list[dict[str, Any]]" in state_source
        assert "rag_results: list[dict[str, Any]]" in state_source


def test_all_rag_agents_expose_metadata_and_context_as_state_evidence():
    roots = [ROOT / "templates", ROOT / "Tuning-Performance"]
    agents = sorted(
        path
        for root in roots
        for path in root.glob("**/app/agents/*.py")
        if '"rag": rag_metadata' in path.read_text(encoding="utf-8")
    )
    assert agents
    for path in agents:
        source = path.read_text(encoding="utf-8")
        assert '"rag_context": rag_context' in source, path
        assert '"rag_results": [{' in source, path


def test_templates_and_tuning_expose_rag_results_in_api_and_telemetry():
    roots = [ROOT / "templates", ROOT / "Tuning-Performance"]
    mains = sorted(path for root in roots for path in root.glob("**/app/main.py"))
    graphs = sorted(path for root in roots for path in root.glob("**/app/workflows/agent_graph.py"))
    assert mains and graphs
    for path in mains:
        assert '"rag_results": result.get("rag_results")' in path.read_text(encoding="utf-8"), path
    for path in graphs:
        assert '"rag_results": state.get("rag_results", [])' in path.read_text(encoding="utf-8"), path


def test_all_tuning_envs_expose_complete_kbdb_configuration():
    envs = sorted((ROOT / "Tuning-Performance").glob("**/.env.example"))
    assert envs
    required = (
        "RAG_PROVIDER=standard",
        "KBDB_DB_USER=",
        "KBDB_DB_DSN=",
        "KBDB_IDENTIFY_DOCUMENT=true",
        "KBDB_STORE_QUERY=true",
        "KBDB_IDENTIFY_TOP_N=3",
        "KBDB_GROUNDED_ONLY=true",
    )
    for path in envs:
        source = path.read_text(encoding="utf-8")
        for setting in required:
            assert setting in source, (path, setting)
