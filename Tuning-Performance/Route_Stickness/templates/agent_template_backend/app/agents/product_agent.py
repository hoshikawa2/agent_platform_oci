from app.agents.prompting import apply_agent_profile_prompt
from app.agents.runtime import AgentRuntimeMixin


class ProductAgent(AgentRuntimeMixin):
    name = "productAgent"

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
            "IC.PRODUCT_AGENT_STARTED",
            state,
            {"business_component": "produtos"},
            component="agent.product.start",
        )

        tool_context = await self._collect_tool_context(state)
        if tool_context:
            await self._emit_ic(
                "IC.PRODUCT_MCP_CONTEXT_COLLECTED",
                state,
                {"tool_result_count": len(tool_context)},
                component="agent.product.mcp",
            )

        state["mcp_results"] = tool_context
        clarification_message = self.transaction_clarification_message(state)
        if clarification_message:
            return {
                "answer": f"[{self.__class__.__name__}] {clarification_message}",
                "next_state": state.get("next_state") or "COLLECTING_PARAMETERS",
                "mcp_results": tool_context,
                **self.transaction_state_patch(state),
            }

        confirmation_message = self.transaction_confirmation_message(state)
        if confirmation_message:
            result = {
                "answer": f"[{self.__class__.__name__}] {confirmation_message}",
                "next_state": state.get("next_state"),
                "mcp_results": tool_context,
                **self.transaction_state_patch(state),
            }
            return result

        direct_answer = self.build_direct_mcp_answer(state, tool_context, agent_label="ProductAgent")
        if direct_answer:
            return {
                "answer": direct_answer,
                "next_state": state.get("next_state") or "ACTIVE",
                "mcp_results": tool_context,
                "rag": {"enabled": False, "skipped": True, "reason": "direct_mcp_answer"},
                **self.transaction_state_patch(state),
            }

        rag_context, rag_metadata = await self._retrieve_rag_context(state)
        if rag_metadata.get("enabled"):
            await self._emit_ic(
                "IC.PRODUCT_RAG_CONTEXT_RETRIEVED",
                state,
                {
                    "document_count": rag_metadata.get("document_count"),
                    "graph_neighbors": rag_metadata.get("graph_neighbors"),
                    "latency_ms": rag_metadata.get("latency_ms"),
                },
                component="agent.product.rag",
            )

        # Prepara ConversationSummaryMemory antes de montar o prompt.
        # O build_messages() do framework injeta resumo + últimas mensagens quando habilitado.
        await self.prepare_memory_context(state)

        messages = self.build_messages(
            state,
            system_prompt=apply_agent_profile_prompt(
                state,
                "Você é um agente especialista em produtos, planos e serviços. Explique sem fazer oferta proativa e sem executar ações sem confirmação. Use dados MCP quando disponíveis.",
            ),
            mcp_results=tool_context,
            rag_context=rag_context,
            rag_metadata=rag_metadata,
        )

        answer = await self._invoke_llm_cached(state, "ProductAgent", messages)
        result = {
            "answer": f"[ProductAgent] {answer}",
            "next_state": "PRODUCT_ACTIVE",
            "mcp_results": tool_context,
            "rag": rag_metadata,
            "memory_context_metadata": state.get("memory_context_metadata"),
            **self.transaction_state_patch(state),
        }

        await self._emit_ic(
            "IC.PRODUCT_AGENT_COMPLETED",
            state,
            {
                "answer_chars": len(result.get("answer") or ""),
                "has_mcp_results": bool(tool_context),
                "rag_enabled": bool(rag_metadata.get("enabled")),
                "memory_context": state.get("memory_context_metadata"),
            },
            component="agent.product.completed",
        )
        return result

    async def _collect_tool_context(self, state):
        return await self._collect_mcp_context(state)
