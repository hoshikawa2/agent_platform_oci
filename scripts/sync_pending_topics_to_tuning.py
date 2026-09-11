"""Propaga o contrato nativo de pending_topics às cópias de Tuning-Performance."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, path: Path) -> str:
    if old not in text:
        raise RuntimeError(f"Marcador não encontrado em {path}: {old[:60]!r}")
    return text.replace(old, new, 1)


def update_state(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "    pending_topics: list[dict[str, Any]]" not in text:
        text = replace_once(
            text,
            "    supervisor_results: list[dict[str, Any]]\n",
            "    supervisor_results: list[dict[str, Any]]\n"
            "    pending_topics: list[dict[str, Any]]\n"
            "    handled_topics: list[dict[str, Any]]\n",
            path,
        )
    if "    rag_results: list[dict[str, Any]]" not in text:
        text = replace_once(
            text,
            "    mcp_results: list[dict[str, Any]]\n",
            "    mcp_results: list[dict[str, Any]]\n"
            "    rag_results: list[dict[str, Any]]\n",
            path,
        )
    path.write_text(text, encoding="utf-8")


def update_graph(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "from agent_framework.routing.pending_topics import drain_pending_topics" in text:
        return
    text = replace_once(
        text,
        "from agent_framework.routing.enterprise_router import EnterpriseRouter\n",
        "from agent_framework.routing.enterprise_router import EnterpriseRouter\n"
        "from agent_framework.routing.pending_topics import drain_pending_topics\n",
        path,
    )
    text = replace_once(
        text,
        "                } if decision.method == \"continuity\" else {},\n            }\n\n    async def billing_agent",
        "                } if decision.method == \"continuity\" else {},\n"
        "                \"pending_topics\": (\n"
        "                    (decision.metadata or {}).get(\"multi_intent_plan\", {}).get(\"operations\", [])[1:]\n"
        "                    if (decision.metadata or {}).get(\"multi_intent_plan\") else []\n"
        "                ),\n"
        "            }\n\n    async def billing_agent",
        path,
    )
    marker = "    async def output_supervisor(self, state):"
    before, output = text.split(marker, 1)
    old = """        if not bool(getattr(self.settings, \"ENABLE_OUTPUT_SUPERVISOR\", True)):
            return {
                \"output_guardrails_already_applied\": False,
                \"supervisor_action\": \"disabled\",
                \"supervisor_attempt\": int(state.get(\"supervisor_attempt\", 0)),
            }

        candidate = state.get(\"answer\") or \"\"
"""
    new = """        drained = await drain_pending_topics(
            state,
            str(state.get(\"answer\") or \"\"),
            {
                \"billing_agent\": self.billing.run,
                \"product_agent\": self.product.run,
                \"orders_agent\": self.orders.run,
                \"support_agent\": self.support.run,
            },
        )
        candidate = drained.answer
        if not bool(getattr(self.settings, \"ENABLE_OUTPUT_SUPERVISOR\", True)):
            return {
                \"answer\": candidate,
                \"final_answer\": candidate,
                \"pending_topics\": drained.pending_topics,
                \"handled_topics\": drained.handled_topics,
                \"output_guardrails_already_applied\": False,
                \"supervisor_action\": \"disabled\",
                \"supervisor_attempt\": int(state.get(\"supervisor_attempt\", 0)),
            }

"""
    output = replace_once(output, old, new, path)
    output = replace_once(
        output,
        "                \"output_guardrails_already_applied\": True,\n",
        "                \"output_guardrails_already_applied\": True,\n"
        "                \"pending_topics\": drained.pending_topics,\n"
        "                \"handled_topics\": drained.handled_topics,\n",
        path,
    )
    path.write_text(before + marker + output, encoding="utf-8")


def update_evidence_propagation(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = '                "handled_topics": drained.handled_topics,\n'
    replacement = marker + '                "mcp_results": drained.mcp_results,\n'
    if replacement in text:
        return
    if marker not in text:
        raise RuntimeError(f"Marcador de evidências não encontrado em {path}")
    path.write_text(text.replace(marker, replacement), encoding="utf-8")


def update_guardrail_evidence_context(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "        context = {\n            **(state.get(\"context\") or {}),\n"
    addition = (
        marker
        + '            "evidence": drained.mcp_results or (state.get("context") or {}).get("evidence"),\n'
        + '            "tool_result": drained.mcp_results or (state.get("context") or {}).get("tool_result"),\n'
        + '            "tool_executed": any(isinstance(item, dict) and item.get("ok") for item in drained.mcp_results),\n'
        + '            "mcp_results": drained.mcp_results,\n'
    )
    if addition in text:
        return
    text = replace_once(text, marker, addition, path)
    path.write_text(text, encoding="utf-8")


def update_rag_propagation(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    mcp_line = '                "mcp_results": drained.mcp_results,\n'
    rag_line = mcp_line + '                "rag_results": drained.rag_results,\n'
    if rag_line not in text:
        if mcp_line not in text:
            raise RuntimeError(f"Marcador MCP não encontrado em {path}")
        text = text.replace(mcp_line, rag_line)
    text = text.replace(
        '            "evidence": drained.mcp_results or (state.get("context") or {}).get("evidence"),\n',
        '            "evidence": (list(drained.mcp_results) + list(drained.rag_results)) or (state.get("context") or {}).get("evidence"),\n',
    )
    marker = '            current_evidence = list(state.get("mcp_results", []) or [])\n'
    addition = marker + '            current_evidence.extend(state.get("rag_results", []) or [])\n'
    if marker in text and addition not in text:
        text = text.replace(marker, addition, 1)
    path.write_text(text, encoding="utf-8")


def update_rag_agents(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = '            "rag": rag_metadata,\n'
    if marker not in text or '            "rag_results": [{\n' in text:
        return
    addition = marker + (
        '            "rag_context": rag_context,\n'
        '            "rag_results": [{\n'
        '                "intent": state.get("intent"),\n'
        '                "agent": self.name,\n'
        '                "source_text": str(state.get("sanitized_input") or state.get("user_text") or ""),\n'
        '                "metadata": rag_metadata,\n'
        '                **({"context": rag_context} if rag_context else {}),\n'
        '            }],\n'
    )
    path.write_text(text.replace(marker, addition, 1), encoding="utf-8")


def update_rag_http_response(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = '                    "mcp_results": result.get("mcp_results"),\n'
    addition = marker + '                    "rag_results": result.get("rag_results"),\n'
    if addition not in text:
        text = replace_once(text, marker, addition, path)
        path.write_text(text, encoding="utf-8")


def update_rag_telemetry(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = '                    "mcp_results": state.get("mcp_results", []),\n'
    addition = marker + '                    "rag_results": state.get("rag_results", []),\n'
    if addition not in text:
        text = replace_once(text, marker, addition, path)
        path.write_text(text, encoding="utf-8")


def update_rag_env(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "KBDB_IDENTIFY_DOCUMENT=" in text:
        return
    marker = "RAG_FILE_GLOBS=*.md,*.txt,*.yaml,*.yml,*.json\n"
    settings_block = """
# RAG / KBDB
# RAG provider: standard (local) ou kbdb (PKG_KB_SERVING.SEARCH_KNOWLEDGE_BASE)
RAG_PROVIDER=standard
# KBDB usa credenciais próprias; não há fallback para ADB_*.
KBDB_DB_USER=
KBDB_DB_PASSWORD=
KBDB_DB_DSN=
KBDB_DB_WALLET_LOCATION=
KBDB_DB_WALLET_PASSWORD=
KBDB_SEARCH_TYPE=hybrid
KBDB_NODE_EXPANSION=true
KBDB_NODE_MAX_RELATED=8
KBDB_GRAPH_CROSS_REF=false
KBDB_MAX_CROSS_REF_HOPS=1
KBDB_DOCUMENT_TYPE=customer_safe
KBDB_METADATA_JSON=
KBDB_MIN_SCORE=
KBDB_IDENTIFY_DOCUMENT=true
KBDB_STORE_QUERY=true
KBDB_IDENTIFY_TOP_N=3
RAG_GROUNDED_ONLY=false
KBDB_GROUNDED_ONLY=true
"""
    if marker in text:
        text = text.replace(marker, marker + "\n" + settings_block, 1)
    else:
        text = text.rstrip() + "\n\n" + settings_block
    path.write_text(text, encoding="utf-8")


def main() -> None:
    tuning = ROOT / "Tuning-Performance"
    states = sorted(tuning.glob("**/app/state.py"))
    graphs = sorted(tuning.glob("**/app/workflows/agent_graph.py"))
    agents = sorted(tuning.glob("**/app/agents/*.py"))
    mains = sorted(tuning.glob("**/app/main.py"))
    envs = sorted(tuning.glob("**/.env.example"))
    for path in states:
        update_state(path)
    for path in graphs:
        update_graph(path)
        update_evidence_propagation(path)
        update_guardrail_evidence_context(path)
        update_rag_propagation(path)
        update_rag_telemetry(path)
    for path in agents:
        update_rag_agents(path)
    for path in mains:
        update_rag_http_response(path)
    for path in envs:
        update_rag_env(path)
    print(f"pending_topics/RAG sincronizado: {len(states)} states, {len(graphs)} graphs, {len(agents)} agents, {len(mains)} APIs, {len(envs)} envs")


if __name__ == "__main__":
    main()
