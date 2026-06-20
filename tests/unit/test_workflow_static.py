from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / 'agent_template_backend' / 'app' / 'workflows' / 'agent_graph.py'

def test_workflow_uses_framework_checkpointer_not_memory_saver():
    src = WORKFLOW.read_text()
    assert 'create_langgraph_checkpointer(self.settings)' in src
    assert 'MemorySaver()' not in src

def test_workflow_wraps_nodes_with_langgraph_telemetry():
    src = WORKFLOW.read_text()
    assert 'self._node("input_guardrails", self.input_guardrails)' in src
    assert 'async with self.langgraph_telemetry.node(name, state)' in src
