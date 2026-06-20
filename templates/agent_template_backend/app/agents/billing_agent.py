from app.agents.prompting import apply_agent_profile_prompt
from app.agents.runtime import AgentRuntimeMixin


class BillingAgent(AgentRuntimeMixin):
    name = "billingAgent"

    def __init__(
        self,
        llm,
        telemetry=None,
        tool_router=None,
        rag_service=None,
        cache=None,
        settings=None,
        observer=None,
        memory=None,
        summary_memory=None,
    ):
        self.llm = llm
        self.telemetry = telemetry
        self.tool_router = tool_router
        self.rag_service = rag_service
        self.cache = cache
        self.settings = settings
        self.observer = observer
        self.memory = memory
        self.summary_memory = summary_memory

    async def run(self, state):
        await self._emit_ic(
            "IC.BILLING_AGENT_STARTED",
            state,
            {"business_component": "faturas"},
            component="agent.billing.start",
        )

        tool_context = await self._collect_tool_context(state)
        if tool_context:
            await self._emit_ic(
                "IC.BILLING_MCP_CONTEXT_COLLECTED",
                state,
                {"tool_result_count": len(tool_context)},
                component="agent.billing.mcp",
            )

        rag_context, rag_metadata = await self._retrieve_rag_context(state)
        if rag_metadata.get("enabled"):
            await self._emit_ic(
                "IC.BILLING_RAG_CONTEXT_RETRIEVED",
                state,
                {
                    "document_count": rag_metadata.get("document_count"),
                    "graph_neighbors": rag_metadata.get("graph_neighbors"),
                    "latency_ms": rag_metadata.get("latency_ms"),
                },
                component="agent.billing.rag",
            )

        # Prepara ConversationSummaryMemory antes de montar o prompt.
        # O build_messages() do framework injeta resumo + últimas mensagens quando habilitado.
        await self.prepare_memory_context(state)

        messages = self.build_messages(
            state,
            system_prompt=apply_agent_profile_prompt(
                state,
                "Você é um agente especialista em faturas. Responda com clareza, objetividade e sem sugerir ações não solicitadas. Use dados MCP quando disponíveis.",
            ),
            mcp_results=tool_context,
            rag_context=rag_context,
            rag_metadata=rag_metadata,
        )

        answer = await self._invoke_llm_cached(state, "BillingAgent", messages)
        result = {
            "answer": f"[BillingAgent] {answer}",
            "next_state": "BILLING_ACTIVE",
            "mcp_results": tool_context,
            "rag": rag_metadata,
            "memory_context_metadata": state.get("memory_context_metadata"),
        }

        await self._emit_ic(
            "IC.BILLING_AGENT_COMPLETED",
            state,
            {
                "answer_chars": len(result.get("answer") or ""),
                "has_mcp_results": bool(tool_context),
                "rag_enabled": bool(rag_metadata.get("enabled")),
                "memory_context": state.get("memory_context_metadata"),
            },
            component="agent.billing.completed",
        )
        return result

    async def _collect_tool_context(self, state):
        return await self._collect_mcp_context(state)
