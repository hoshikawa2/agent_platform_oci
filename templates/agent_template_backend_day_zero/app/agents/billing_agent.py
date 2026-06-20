"""
DAY ZERO TEMPLATE - BillingAgent

Esqueleto mínimo já compatível com ConversationSummaryMemory.
Substitua o prompt e a regra de negócio conforme o seu agente.
"""

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
        # OPCIONAL: habilite quando seu agente precisar de MCP/RAG.
        tool_context = []
        rag_context = None
        rag_metadata = {}

        # Prepara a memória resumida antes do prompt.
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
        return {
            "answer": answer,
            "next_state": "DAY_ZERO_ACTIVE",
            "mcp_results": tool_context,
            "rag": rag_metadata,
            "memory_context_metadata": state.get("memory_context_metadata"),
        }

    async def _collect_tool_context(self, state):
        return await self._collect_mcp_context(state)
