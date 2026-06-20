from agent_framework.checkpoints.langgraph_saver import create_langgraph_checkpointer
from langgraph.graph import END, START, StateGraph

from agent_framework.guardrails.pipeline import GuardrailPipeline
from agent_framework.guardrails.output_supervisor import OutputSupervisor
from agent_framework.guardrails.rail_action import RailAction
from agent_framework.guardrails.rail_result import RailResult
from agent_framework.judges.judge import JudgePipeline
from agent_framework.routing.enterprise_router import EnterpriseRouter
from agent_framework.supervisor.supervisor import Supervisor
from agent_framework.observability.workflow_events import WorkflowTelemetry
from agent_framework.observability.guardrail_events import GuardrailTelemetry
from agent_framework.observability.judge_events import JudgeTelemetry
from agent_framework.observability.langgraph_telemetry import LangGraphDeepTelemetry
from agent_framework.observability.observer import AgentObserver
from app.agents.billing_agent import BillingAgent
from app.agents.product_agent import ProductAgent
from app.agents.orders_agent import OrdersAgent
from app.agents.support_agent import SupportAgent
from app.state import AgentState
from agent_framework.rag.rag_service import RagService
from agent_framework.rag.embedding_provider import create_embedding_provider
from agent_framework.cache.cache import create_cache


class LegacyOutputGuardrailRail:
    """Adapter: reutiliza GuardrailPipeline.run_output dentro do OutputSupervisor novo.

    O framework antigo retornava decisões allowed=True/False. O OutputSupervisor
    corporativo trabalha com RailAction (allow/sanitize/retry/block/handover).
    Este adapter evita reescrever todos os rails agora e mantém compatibilidade.
    """

    code = "LEGACY_OUTPUT_GUARDRAILS"

    def __init__(self, pipeline: GuardrailPipeline):
        self.pipeline = pipeline

    async def evaluate(self, candidate: str, context: dict):
        final, decisions = await self.pipeline.run_output(candidate, context)
        serialized = [d.model_dump() for d in decisions]

        blocked = [d for d in decisions if not getattr(d, "allowed", True)]
        if blocked:
            first = blocked[0]
            code = (getattr(first, "code", "") or "").upper()
            action = RailAction.RETRY if code in {"REVPREC", "CMP", "SCO", "GND"} else RailAction.BLOCK
            return RailResult(
                code=code or self.code,
                action=action,
                reason=getattr(first, "reason", "Resposta bloqueada por guardrail de saída"),
                guidance=getattr(first, "reason", "Regerar resposta seguindo as políticas de saída."),
                sanitized_text=final,
                metadata={"legacy_decisions": serialized},
            )

        if final != candidate:
            return RailResult(
                code=self.code,
                action=RailAction.SANITIZE,
                reason="Resposta sanitizada por guardrail de saída legado.",
                sanitized_text=final,
                metadata={"legacy_decisions": serialized},
            )

        return RailResult(
            code=self.code,
            action=RailAction.ALLOW,
            reason="Resposta aprovada pelos guardrails de saída legados.",
            sanitized_text=final,
            metadata={"legacy_decisions": serialized},
        )


class AgentWorkflow:
    """Workflow principal com dois modos de roteamento.

    Modos suportados por configuração:
      ROUTING_MODE=router
        input_guardrails -> routing_decision/EnterpriseRouter -> 1 agente -> output_guardrails

      ROUTING_MODE=supervisor
        input_guardrails -> routing_decision/Supervisor -> supervisor_agent -> N agentes -> consolidação

    Em ambos os modos, memória/checkpoint/session usam tenant_id:agent_id:session_id.
    """

    def __init__(self, llm, memory, telemetry, analytics, settings, observer: AgentObserver | None = None, tool_router=None, summary_memory=None):
        self.llm = llm
        self.memory = memory
        self.telemetry = telemetry
        self.analytics = analytics
        self.observer = observer or AgentObserver(analytics=analytics)
        self.settings = settings
        self.tool_router = tool_router
        self.summary_memory = summary_memory
        self.guardrails = GuardrailPipeline(
            observer=self.observer,
            enable_parallel=bool(getattr(settings, "ENABLE_PARALLEL_GUARDRAILS", True)),
            fail_fast=bool(getattr(settings, "GUARDRAILS_FAIL_FAST", True)),
        )
        self.output_supervisor_engine = OutputSupervisor(
            rails=[LegacyOutputGuardrailRail(self.guardrails)],
            observer=self.observer,
            max_retries=int(getattr(settings, "OUTPUT_SUPERVISOR_MAX_RETRIES", 3)),
            enable_parallel=bool(getattr(settings, "ENABLE_PARALLEL_GUARDRAILS", True)),
            fail_fast=bool(getattr(settings, "GUARDRAILS_FAIL_FAST", True)),
        )
        self.judges = JudgePipeline()
        self.supervisor = Supervisor()
        self.workflow_telemetry = WorkflowTelemetry(telemetry)
        self.guardrail_telemetry = GuardrailTelemetry(telemetry)
        self.judge_telemetry = JudgeTelemetry(telemetry)
        self.langgraph_telemetry = LangGraphDeepTelemetry(telemetry)
        self.cache = create_cache(settings)
        self.embedding_provider = create_embedding_provider(settings)
        self.rag_service = RagService(settings, embedding_provider=self.embedding_provider, telemetry=telemetry)
        self.router = EnterpriseRouter(settings, llm=llm, telemetry=telemetry)
        agent_kwargs = {"telemetry": telemetry, "tool_router": getattr(self, "tool_router", None), "rag_service": self.rag_service, "cache": self.cache, "settings": settings, "observer": self.observer, "memory": memory, "summary_memory": summary_memory}
        self.billing = BillingAgent(llm, **agent_kwargs)
        self.product = ProductAgent(llm, **agent_kwargs)
        self.orders = OrdersAgent(llm, **agent_kwargs)
        self.support = SupportAgent(llm, **agent_kwargs)
        self.graph = self._build_graph()

    def _node(self, name, fn):
        async def _wrapped(state):
            async with self.langgraph_telemetry.node(name, state):
                return await fn(state)
        return _wrapped

    def _build_graph(self):
        builder = StateGraph(AgentState)
        builder.add_node("input_guardrails", self._node("input_guardrails", self.input_guardrails))
        builder.add_node("routing_decision", self._node("routing_decision", self.routing_decision))
        builder.add_node("billing_agent", self._node("billing_agent", self.billing_agent))
        builder.add_node("product_agent", self._node("product_agent", self.product_agent))
        builder.add_node("orders_agent", self._node("orders_agent", self.orders_agent))
        builder.add_node("support_agent", self._node("support_agent", self.support_agent))
        builder.add_node("handoff", self._node("handoff", self.handoff))
        builder.add_node("supervisor_agent", self._node("supervisor_agent", self.supervisor_agent))
        builder.add_node("output_supervisor", self._node("output_supervisor", self.output_supervisor))
        builder.add_node("output_guardrails", self._node("output_guardrails", self.output_guardrails))
        builder.add_node("judge", self._node("judge", self.judge))
        builder.add_node("supervisor_review", self._node("supervisor_review", self.supervisor_review))
        builder.add_node("persist", self._node("persist", self.persist))

        builder.add_edge(START, "input_guardrails")
        builder.add_conditional_edges(
            "input_guardrails",
            self._after_input_guardrails,
            {"blocked": "persist", "continue": "routing_decision"},
        )
        builder.add_conditional_edges(
            "routing_decision",
            lambda s: s.get("route", "billing_agent"),
            {
                "billing_agent": "billing_agent",
                "product_agent": "product_agent",
                "orders_agent": "orders_agent",
                "support_agent": "support_agent",
                "handoff": "handoff",
                "supervisor_agent": "supervisor_agent",
            },
        )
        builder.add_edge("billing_agent", "output_supervisor")
        builder.add_edge("product_agent", "output_supervisor")
        builder.add_edge("orders_agent", "output_supervisor")
        builder.add_edge("support_agent", "output_supervisor")
        builder.add_edge("handoff", "output_supervisor")
        builder.add_edge("supervisor_agent", "output_supervisor")
        builder.add_edge("output_supervisor", "output_guardrails")
        builder.add_edge("output_guardrails", "judge")
        builder.add_edge("judge", "supervisor_review")
        builder.add_edge("supervisor_review", "persist")
        builder.add_edge("persist", END)

        return builder.compile(checkpointer=create_langgraph_checkpointer(self.settings))

    def _after_input_guardrails(self, state):
        return "blocked" if state.get("blocked") else "continue"

    async def input_guardrails(self, state):
        async with self.telemetry.span(
            "workflow.input_guardrails",
            session_id=state.get("conversation_key") or state.get("session_id"),
            input=state.get("user_text"),
        ):
            history_texts = [m.get("content", "") for m in state.get("history", [])]
            await self.observer.emit_grl(
                "001",
                {
                    "session_id": state.get("conversation_key") or state.get("session_id"),
                    "tenant_id": state.get("tenant_id"),
                    "agent_id": state.get("agent_id"),
                    "phase": "input",
                },
                component="workflow.input_guardrails.start",
            )
            sanitized, decisions = await self.guardrails.run_input(
                state["user_text"],
                {
                    **(state.get("context") or {}),
                    "history_texts": history_texts,
                    "tenant_id": state.get("tenant_id"),
                    "agent_id": state.get("agent_id"),
                    "agent_profile": state.get("agent_profile") or {},
                },
            )
            for _decision in decisions:
                await self.guardrail_telemetry.evaluated("input", _decision)
                await self.observer.emit_grl(
                    "002" if _decision.allowed else "004",
                    {
                        "session_id": state.get("conversation_key") or state.get("session_id"),
                        "tenant_id": state.get("tenant_id"),
                        "agent_id": state.get("agent_id"),
                        "phase": "input",
                        "rail_code": getattr(_decision, "code", None),
                        "allowed": bool(_decision.allowed),
                        "reason": getattr(_decision, "reason", None),
                    },
                    component="workflow.input_guardrails.decision",
                )
                if not _decision.allowed:
                    await self.guardrail_telemetry.blocked("input", _decision)
            await self.telemetry.event(
                "guardrails.input.completed",
                {
                    "session_id": state.get("conversation_key") or state.get("session_id"),
                    "tenant_id": state.get("tenant_id"),
                    "agent_id": state.get("agent_id"),
                    "decisions": [d.model_dump() for d in decisions],
                },
            )
            await self.observer.emit_grl(
                "009",
                {
                    "session_id": state.get("conversation_key") or state.get("session_id"),
                    "tenant_id": state.get("tenant_id"),
                    "agent_id": state.get("agent_id"),
                    "phase": "input",
                    "blocked": any(not d.allowed for d in decisions),
                    "decision_count": len(decisions),
                },
                component="workflow.input_guardrails.final",
            )
            if any(not d.allowed for d in decisions):
                return {
                    "sanitized_input": sanitized,
                    "answer": "Não consegui seguir com essa mensagem por regra de segurança.",
                    "final_answer": "Não consegui seguir com essa mensagem por regra de segurança.",
                    "guardrail_decisions": [d.model_dump() for d in decisions],
                    "route": "blocked",
                    "blocked": True,
                }
            return {
                "sanitized_input": sanitized,
                "guardrail_decisions": [d.model_dump() for d in decisions],
                "blocked": False,
            }

    async def routing_decision(self, state):
        mode = getattr(self.settings, "ROUTING_MODE", "router")
        async with self.telemetry.span(
            "workflow.routing_decision",
            session_id=state.get("conversation_key") or state.get("session_id"),
            input={
                "mode": mode,
                "text": state.get("sanitized_input") or state.get("user_text"),
                "previous_state": state.get("next_state"),
            },
        ):
            if mode == "supervisor":
                plan = await self.supervisor.route_plan(state)
                await self.langgraph_telemetry.edge("routing_decision", "supervisor_agent", state, {"method": "supervisor", "intent": plan.intent, "confidence": plan.confidence})
                return {
                    "route": "supervisor_agent",
                    "intent": plan.intent,
                    "supervisor_plan": {
                        "agents": plan.agents,
                        "intent": plan.intent,
                        "confidence": plan.confidence,
                        "reason": plan.reason,
                        "metadata": plan.metadata,
                    },
                    "route_decision": {
                        "route": "supervisor_agent",
                        "agent": "supervisor",
                        "intent": plan.intent,
                        "confidence": plan.confidence,
                        "reason": plan.reason,
                        "method": "supervisor",
                        "metadata": plan.metadata,
                    },
                }

            decision = await self.router.route(state)
            await self.langgraph_telemetry.edge("routing_decision", decision.route, state, {"method": getattr(decision, "method", None), "intent": decision.intent, "confidence": decision.confidence})
            await self.observer.emit_ic(
                "ROUTE_SELECTED",
                {
                    "session_id": state.get("conversation_key") or state.get("session_id"),
                    "tenant_id": state.get("tenant_id"),
                    "agent_id": state.get("agent_id"),
                    "route": decision.route,
                    "intent": decision.intent,
                    "confidence": decision.confidence,
                    "method": getattr(decision, "method", None),
                },
                component="workflow.routing_decision",
            )
            return {
                "route": decision.route,
                "intent": decision.intent,
                "route_decision": decision.model_dump(mode="json"),
                "domain": decision.domain,
                "mcp_tools": decision.mcp_tools,
                "next_state": decision.next_state,
            }

    async def billing_agent(self, state):
        async with self.langgraph_telemetry.node("billing_agent", state):
            async with self.telemetry.span(
                "workflow.agent.billing",
                session_id=state.get("conversation_key") or state.get("session_id"),
                input={"intent": state.get("intent")},
            ):
                return await self.billing.run(state)

    async def product_agent(self, state):
        async with self.langgraph_telemetry.node("product_agent", state):
            async with self.telemetry.span(
                "workflow.agent.product",
                session_id=state.get("conversation_key") or state.get("session_id"),
                input={"intent": state.get("intent")},
            ):
                return await self.product.run(state)

    async def orders_agent(self, state):
        async with self.langgraph_telemetry.node("orders_agent", state):
            async with self.telemetry.span(
                    "workflow.agent.orders",
                    session_id=state.get("conversation_key") or state.get("session_id"),
                    input={"intent": state.get("intent")},
            ):
                return await self.orders.run(state)


    async def support_agent(self, state):
        async with self.langgraph_telemetry.node("support_agent", state):
            async with self.telemetry.span(
                    "workflow.agent.support",
                    session_id=state.get("conversation_key") or state.get("session_id"),
                    input={"intent": state.get("intent")},
            ):
                return await self.support.run(state)

    async def supervisor_agent(self, state):
        """Executa um ou mais agentes no modo supervisor e consolida a resposta.

        Este nó mantém o desenho de supervisor sem obrigar o restante do workflow
        a conhecer quantos agentes foram acionados. Cada execução especializada
        recebe o mesmo estado, mas com route/active_agent atualizados.
        """
        plan = state.get("supervisor_plan") or {}
        agents = plan.get("agents") or ["billing_agent"]
        handlers = {
            "billing_agent": self.billing.run,
            "product_agent": self.product.run,
            "orders_agent": self.orders.run,
            "support_agent": self.support.run,
        }
        partials = []
        mcp_results = []
        async with self.telemetry.span(
            "workflow.supervisor_agent",
            session_id=state.get("conversation_key") or state.get("session_id"),
            input={"agents": agents, "intent": state.get("intent")},
        ):
            for agent_name in agents:
                handler = handlers.get(agent_name)
                if handler is None:
                    continue
                child_state = {**state, "route": agent_name, "active_agent": agent_name}
                result = await handler(child_state)
                partials.append({"agent": agent_name, "answer": result.get("answer", "")})
                mcp_results.extend(result.get("mcp_results") or [])

        if len(partials) == 1:
            answer = partials[0]["answer"]
        else:
            joined = "\n\n".join(f"{p['agent']}: {p['answer']}" for p in partials)
            answer = (
                "[Supervisor] Consolidação de múltiplos agentes acionados.\n"
                f"{joined}"
            )
        return {
            "answer": answer,
            "supervisor_results": partials,
            "mcp_results": mcp_results,
            "next_state": "SUPERVISOR_ACTIVE",
        }

    async def handoff(self, state):
        async with self.telemetry.span("workflow.handoff", session_id=state.get("session_id")):
            target = (state.get("route_decision") or {}).get("metadata", {}).get("target_agent")
            answer = (
                "Vou redirecionar sua solicitação para o especialista correto. "
                f"Destino sugerido: {target or 'agente especializado'}."
            )
            return {"answer": answer}

    async def output_supervisor(self, state):
        """Valida a resposta candidata com o OutputSupervisor corporativo.

        Este nó não substitui o roteador/supervisor multiagente. Ele roda após o
        agente gerar `answer` e antes dos judges/persistência, produzindo campos
        supervisor_* no state e eventos GRL.001..GRL.009 via AgentObserver.
        """
        if not bool(getattr(self.settings, "ENABLE_OUTPUT_SUPERVISOR", True)):
            return {
                "output_guardrails_already_applied": False,
                "supervisor_action": "disabled",
                "supervisor_attempt": int(state.get("supervisor_attempt", 0)),
            }

        candidate = state.get("answer") or ""
        context = {
            **(state.get("context") or {}),
            "tenant_id": state.get("tenant_id"),
            "agent_id": state.get("agent_id"),
            "session_id": state.get("conversation_key") or state.get("session_id"),
            "route": state.get("route"),
            "intent": state.get("intent"),
            "supervisor_attempt": int(state.get("supervisor_attempt", 0)),
        }
        async with self.telemetry.span(
            "workflow.output_supervisor",
            session_id=state.get("conversation_key") or state.get("session_id"),
            input=candidate,
        ):
            decision = await self.output_supervisor_engine.evaluate(candidate, context)
            action = decision.action.value
            await self.telemetry.event(
                "output_supervisor.completed",
                {
                    "session_id": context["session_id"],
                    "tenant_id": state.get("tenant_id"),
                    "agent_id": state.get("agent_id"),
                    "action": action,
                    "approved": decision.approved,
                    "guidance": decision.guidance,
                },
            )

            await self.observer.emit_ic(
                "IC.OUTPUT_SUPERVISOR_COMPLETED",
                {
                    "session_id": context["session_id"],
                    "tenant_id": state.get("tenant_id"),
                    "agent_id": state.get("agent_id"),
                    "route": state.get("route"),
                    "intent": state.get("intent"),
                    "action": action,
                    "approved": decision.approved,
                    "result_count": len(decision.results),
                },
                component="workflow.output_supervisor",
            )

            if decision.action in {RailAction.ALLOW, RailAction.SANITIZE, RailAction.OBSERVE}:
                final_answer = decision.candidate
            elif decision.action == RailAction.HANDOVER:
                final_answer = "Vou encaminhar seu atendimento para continuidade com um especialista."
            else:
                final_answer = decision.fallback_message

            return {
                "answer": final_answer,
                "final_answer": final_answer,
                "supervisor_action": action,
                "supervisor_guidance": decision.guidance,
                "supervisor_attempt": int(state.get("supervisor_attempt", 0)) + (1 if decision.action == RailAction.RETRY else 0),
                "supervisor_handover_reason": decision.handover_reason,
                "output_supervisor_results": [
                    {
                        "code": r.code,
                        "action": r.action.value,
                        "reason": r.reason,
                        "guidance": r.guidance,
                        "metadata": r.metadata,
                    }
                    for r in decision.results
                ],
                "output_guardrails_already_applied": True,
                "guardrail_decisions": state.get("guardrail_decisions", [])
                + [item for r in decision.results for item in (r.metadata or {}).get("legacy_decisions", [])],
            }

    async def output_guardrails(self, state):
        if state.get("output_guardrails_already_applied"):
            return {"final_answer": state.get("final_answer") or state.get("answer") or ""}

        async with self.telemetry.span(
            "workflow.output_guardrails",
            session_id=state.get("conversation_key") or state.get("session_id"),
            input=state.get("answer"),
        ):
            await self.observer.emit_grl(
                "001",
                {
                    "session_id": state.get("conversation_key") or state.get("session_id"),
                    "tenant_id": state.get("tenant_id"),
                    "agent_id": state.get("agent_id"),
                    "phase": "output",
                    "route": state.get("route"),
                    "intent": state.get("intent"),
                },
                component="workflow.output_guardrails.start",
            )
            final, decisions = await self.guardrails.run_output(
                state["answer"], state.get("context", {})
            )
            for _decision in decisions:
                await self.guardrail_telemetry.evaluated("output", _decision)
                await self.observer.emit_grl(
                    "002" if _decision.allowed else "004",
                    {
                        "session_id": state.get("conversation_key") or state.get("session_id"),
                        "tenant_id": state.get("tenant_id"),
                        "agent_id": state.get("agent_id"),
                        "phase": "output",
                        "rail_code": getattr(_decision, "code", None),
                        "allowed": bool(_decision.allowed),
                        "reason": getattr(_decision, "reason", None),
                    },
                    component="workflow.output_guardrails.decision",
                )
                if not _decision.allowed:
                    await self.guardrail_telemetry.blocked("output", _decision)
            await self.telemetry.event(
                "guardrails.output.completed",
                {
                    "session_id": state.get("conversation_key") or state.get("session_id"),
                    "tenant_id": state.get("tenant_id"),
                    "agent_id": state.get("agent_id"),
                    "decisions": [d.model_dump() for d in decisions],
                },
            )
            await self.observer.emit_grl(
                "009",
                {
                    "session_id": state.get("conversation_key") or state.get("session_id"),
                    "tenant_id": state.get("tenant_id"),
                    "agent_id": state.get("agent_id"),
                    "phase": "output",
                    "blocked": any(not d.allowed for d in decisions),
                    "decision_count": len(decisions),
                },
                component="workflow.output_guardrails.final",
            )
            return {
                "final_answer": final,
                "guardrail_decisions": state.get("guardrail_decisions", [])
                + [d.model_dump() for d in decisions],
            }

    async def judge(self, state):
        async with self.telemetry.span(
            "workflow.judge",
            session_id=state.get("conversation_key") or state.get("session_id"),
            input={"question": state.get("user_text"), "answer": state.get("final_answer")},
        ):
            results = await self.judges.evaluate_all(
                state["user_text"], state["final_answer"], state.get("context", {})
            )
            for _result in results:
                await self.judge_telemetry.evaluated(_result)
            await self.telemetry.event(
                "judges.completed",
                {
                    "session_id": state.get("conversation_key") or state.get("session_id"),
                    "tenant_id": state.get("tenant_id"),
                    "agent_id": state.get("agent_id"),
                    "results": [r.model_dump() for r in results],
                },
            )
            return {"judge_results": [r.model_dump() for r in results]}

    async def supervisor_review(self, state):
        async with self.telemetry.span(
            "workflow.supervisor_review",
            session_id=state.get("conversation_key") or state.get("session_id"),
            input=state.get("final_answer"),
        ):
            ok, answer = await self.supervisor.review(
                state["final_answer"], state.get("context", {})
            )
            await self.telemetry.event(
                "supervisor.review.completed",
                {"session_id": state.get("session_id"), "approved": ok},
            )
            return {"final_answer": answer if ok else answer}

    async def persist(self, state):
        async with self.telemetry.span(
            "workflow.persist",
            session_id=state.get("conversation_key") or state.get("session_id"),
            input={"route": state.get("route"), "intent": state.get("intent")},
        ):
            await self.observer.emit_ic(
                "AGENT_COMPLETED",
                {
                    "session_id": state.get("conversation_key") or state["session_id"],
                    "tenant_id": state.get("tenant_id"),
                    "agent_id": state.get("agent_id"),
                    "route": state.get("route"),
                    "intent": state.get("intent"),
                    "route_decision": state.get("route_decision"),
                    "judges": state.get("judge_results", []),
                    "mcp_tools": state.get("mcp_tools", []),
                    "mcp_results": state.get("mcp_results", []),
                },
            )

            await self.observer.emit_noc(
                "006",
                {
                    "session_id": state.get("conversation_key") or state["session_id"],
                    "tenant_id": state.get("tenant_id"),
                    "agent_id": state.get("agent_id"),
                    "route": state.get("route"),
                    "intent": state.get("intent"),
                    "answer_chars": len(state.get("final_answer") or ""),
                },
                component="workflow.persist",
            )

            await self.telemetry.event(
                "agent.completed",
                {
                    "session_id": state.get("conversation_key") or state["session_id"],
                    "tenant_id": state.get("tenant_id"),
                    "agent_id": state.get("agent_id"),
                    "route": state.get("route"),
                    "intent": state.get("intent"),
                    "answer_chars": len(state.get("final_answer") or ""),
                },
            )
            return state

    async def ainvoke(self, state):
        thread_id = state.get("conversation_key") or state["session_id"]
        config = {"configurable": {"thread_id": thread_id}}
        async with self.telemetry.span(
            "workflow.langgraph.ainvoke",
            session_id=state.get("conversation_key") or state.get("session_id"),
            user_id=state.get("context", {}).get("user_id"),
            input={"user_text": state.get("user_text")},
            tags=["langgraph", "agent-workflow", f"routing-mode:{getattr(self.settings, 'ROUTING_MODE', 'router')}",],
        ):
            await self.workflow_telemetry.started("agent_workflow", state)
            await self.observer.emit_noc(
                "001",
                {
                    "session_id": state.get("conversation_key") or state.get("session_id"),
                    "tenant_id": state.get("tenant_id"),
                    "agent_id": state.get("agent_id"),
                    "channel_id": (state.get("context") or {}).get("channel"),
                    "message_id": (state.get("context") or {}).get("message_id"),
                    "ura_call_id": (state.get("context") or {}).get("ura_call_id"),
                },
                component="workflow.ainvoke",
            )
            await self.observer.emit_ic(
                "AGENT_STARTED",
                {
                    "session_id": state.get("conversation_key") or state.get("session_id"),
                    "tenant_id": state.get("tenant_id"),
                    "agent_id": state.get("agent_id"),
                    "channel_id": (state.get("context") or {}).get("channel"),
                    "message_id": (state.get("context") or {}).get("message_id"),
                    "user_text_chars": len(state.get("user_text") or ""),
                },
                component="workflow.ainvoke",
            )
            try:
                result = await self.graph.ainvoke(state, config=config)
                await self.workflow_telemetry.completed("agent_workflow", result)
                return result
            except Exception as exc:
                await self.workflow_telemetry.failed("agent_workflow", exc)
                await self.observer.emit_noc(
                    "005",
                    {
                        "session_id": state.get("conversation_key") or state.get("session_id"),
                        "tenant_id": state.get("tenant_id"),
                        "agent_id": state.get("agent_id"),
                        "error": str(exc),
                        "exception_type": exc.__class__.__name__,
                    },
                    component="workflow.ainvoke",
                )
                raise
