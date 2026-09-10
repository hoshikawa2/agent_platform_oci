"""Propaga o contrato nativo de pending_topics às cópias de Tuning-Performance."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, path: Path) -> str:
    if old not in text:
        raise RuntimeError(f"Marcador não encontrado em {path}: {old[:60]!r}")
    return text.replace(old, new, 1)


def update_state(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "    pending_topics: list[dict[str, Any]]" in text:
        return
    text = replace_once(
        text,
        "    supervisor_results: list[dict[str, Any]]\n",
        "    supervisor_results: list[dict[str, Any]]\n"
        "    pending_topics: list[dict[str, Any]]\n"
        "    handled_topics: list[dict[str, Any]]\n",
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


def main() -> None:
    tuning = ROOT / "Tuning-Performance"
    states = sorted(tuning.glob("**/app/state.py"))
    graphs = sorted(tuning.glob("**/app/workflows/agent_graph.py"))
    for path in states:
        update_state(path)
    for path in graphs:
        update_graph(path)
    print(f"pending_topics sincronizado: {len(states)} states, {len(graphs)} graphs")


if __name__ == "__main__":
    main()
