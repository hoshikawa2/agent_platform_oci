from __future__ import annotations

from agent_framework.llm.structured_output import parse_json_object

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


from agent_framework.memory.summary_memory import MemoryContext, render_recent_messages
from agent_framework.runtime.transaction_parameters import extract_transaction_parameters, parse_transaction_confirmation
from agent_framework.workflows.input_contract import match_expected_input


logger = logging.getLogger(__name__)

_EMPTY_VALUES = (None, "", {}, [])

_ACTIVE_TRANSACTION_STATUSES = {
    "COLLECTING_PARAMETERS",
    "AWAITING_CONFIRMATION",
    "WORKFLOW_PAUSED",
    "TOOL_RESULT_CLARIFICATION",
    "EXECUTING",
}
_TERMINAL_TRANSACTION_STATUSES = {
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "BLOCKED",
    "OUT_OF_SCOPE",
}


@dataclass(slots=True)
class RuntimeContext:
    """Visão canônica do state para agentes.

    O objetivo desta classe é evitar que cada agente precise conhecer todos os
    possíveis caminhos internos do state/context/session. O framework centraliza
    a ordem de precedência e o agente usa este objeto para ler dados com clareza.
    """

    state: dict[str, Any]
    context: dict[str, Any] = field(default_factory=dict)
    session: dict[str, Any] = field(default_factory=dict)
    session_metadata: dict[str, Any] = field(default_factory=dict)
    business_context: dict[str, Any] = field(default_factory=dict)
    tool_arguments: dict[str, Any] = field(default_factory=dict)
    user_text: str = ""
    sanitized_input: str = ""
    original_text: str = ""

    def pick(self, *names: str, default: Any = None) -> Any:
        """Busca uma chave usando a precedência corporativa.

        Ordem: tool_arguments > business_context > context > session >
        session.metadata > state. Essa ordem faz com que parâmetros explícitos e
        identidade de negócio resolvida prevaleçam sobre dados brutos do canal.
        """
        for name in names:
            for source in (
                self.tool_arguments,
                self.business_context,
                self.context,
                self.session,
                self.session_metadata,
                self.state,
            ):
                if isinstance(source, Mapping) and name in source:
                    value = source.get(name)
                    if value not in _EMPTY_VALUES:
                        return value
        return default

    def as_original_context(self) -> dict[str, Any]:
        """Monta o contexto a ser enviado ao MCPToolRouter."""
        session_id = self.state.get("conversation_key") or self.state.get("session_id") or self.session.get("backend_session_id") or self.session.get("global_session_id")
        return {
            **self.context,
            "session": self.session,
            "session_metadata": self.session_metadata,
            "tenant_id": self.state.get("tenant_id") or self.session.get("tenant_id"),
            "agent_id": self.state.get("agent_id") or self.state.get("route") or self.session.get("active_agent"),
            "session_id": session_id,
            "conversation_key": self.state.get("conversation_key") or session_id,
        }


class MessageBuilder:
    """Builder simples para messages compatível com ChatModel/OpenAI-like."""

    def __init__(self, state: dict[str, Any]):
        self.state = state
        self._messages: list[dict[str, str]] = []

    def system(self, content: str) -> "MessageBuilder":
        if content:
            self._messages.append({"role": "system", "content": str(content)})
        return self

    def user(self, content: str) -> "MessageBuilder":
        if content:
            self._messages.append({"role": "user", "content": str(content)})
        return self

    def assistant(self, content: str) -> "MessageBuilder":
        if content:
            self._messages.append({"role": "assistant", "content": str(content)})
        return self

    def section(self, title: str, value: Any, *, empty: str = "[não informado]") -> str:
        rendered = empty if value in _EMPTY_VALUES else str(value)
        return f"{title}:\n{rendered}"

    def build(self) -> list[dict[str, str]]:
        return list(self._messages)


class AgentRuntimeMixin:
    """Mixin operacional reutilizável para agentes.

    Esta implementação centraliza rotinas comuns que antes ficavam duplicadas em
    agentes reais: leitura canônica de contexto, escolha de tools, montagem de
    argumentos, política de execução de tools, construção de messages, cache LLM,
    RAG e eventos IC/NOC/GRL.
    """

    # ------------------------------------------------------------------
    # Contexto e estado
    # ------------------------------------------------------------------
    def get_runtime_context(self, state: dict[str, Any]) -> RuntimeContext:
        ctx = state.get("context") or {}
        session = ctx.get("session") or {}
        session_metadata = session.get("metadata") or {}
        business_context = ctx.get("business_context") or state.get("business_context") or {}
        tool_arguments = ctx.get("tool_arguments") or state.get("tool_arguments") or {}
        sanitized = state.get("sanitized_input") or state.get("user_text") or ""
        original = (
            ctx.get("message")
            or ctx.get("text")
            or ctx.get("query")
            or session.get("last_user_message")
            or state.get("user_text")
            or sanitized
            or ""
        )
        return RuntimeContext(
            state=state,
            context=ctx,
            session=session,
            session_metadata=session_metadata,
            business_context=business_context if isinstance(business_context, dict) else {},
            tool_arguments=tool_arguments if isinstance(tool_arguments, dict) else {},
            user_text=state.get("user_text") or "",
            sanitized_input=sanitized,
            original_text=original,
        )

    def pick_context_value(self, state: dict[str, Any], *names: str, default: Any = None) -> Any:
        return self.get_runtime_context(state).pick(*names, default=default)

    def normalize_tools_by_intent(
        self,
        state: dict[str, Any],
        *,
        default_tools_by_intent: dict[str, list[str]] | None = None,
        default_intent: str | None = None,
        route: str | None = None,
    ) -> dict[str, Any]:
        """Garante intent/route/tools consistentes para o agente.

        A fonte preferencial de tools continua sendo o EnterpriseRouter via
        state['mcp_tools']. O dicionário default_tools_by_intent é apenas fallback
        para chamadas diretas, testes ou cenários em que o router não injetou
        tools.
        """
        defaults = default_tools_by_intent or {}
        intent = state.get("intent") or default_intent or next(iter(defaults.keys()), None)
        configured_tools = list(state.get("mcp_tools") or [])
        fallback_tools = list(defaults.get(intent, [])) if intent else []
        tools = configured_tools or fallback_tools
        seen: set[str] = set()
        deduped: list[str] = []
        for tool in tools:
            if tool and tool not in seen:
                seen.add(tool)
                deduped.append(tool)
        return {
            **state,
            "route": state.get("route") or route or getattr(self, "name", None),
            "active_agent": state.get("active_agent") or getattr(self, "name", None),
            "intent": intent,
            "mcp_tools": deduped,
        }

    # ------------------------------------------------------------------
    # Observabilidade
    # ------------------------------------------------------------------
    def _event_base(self, state: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
        runtime = self.get_runtime_context(state)
        base = {
            "session_id": state.get("conversation_key") or state.get("session_id") or runtime.session.get("backend_session_id") or runtime.session.get("global_session_id"),
            "tenant_id": state.get("tenant_id") or runtime.session.get("tenant_id"),
            "agent_id": state.get("agent_id") or getattr(self, "name", None),
            "route": state.get("route"),
            "intent": state.get("intent"),
            "message_id": runtime.context.get("message_id"),
            "channel_id": runtime.context.get("channel") or runtime.session.get("channel"),
        }
        base.update(payload or {})
        return base

    async def _emit_ic(self, code: str, state: dict[str, Any], payload: dict[str, Any] | None = None, component: str | None = None) -> None:
        observer = getattr(self, "observer", None)
        if not observer:
            return
        try:
            await observer.emit_ic(code, self._event_base(state, payload), component=component or f"agent.{getattr(self, 'name', 'unknown')}")
        except Exception:
            return

    async def _emit_noc(self, code: str, state: dict[str, Any], payload: dict[str, Any] | None = None, component: str | None = None) -> None:
        observer = getattr(self, "observer", None)
        if not observer:
            return
        try:
            await observer.emit_noc(code, self._event_base(state, payload), component=component or f"agent.{getattr(self, 'name', 'unknown')}")
        except Exception:
            return

    async def _emit_grl(self, code: str, state: dict[str, Any], payload: dict[str, Any] | None = None, component: str | None = None) -> None:
        observer = getattr(self, "observer", None)
        if not observer:
            return
        try:
            await observer.emit_grl(code, self._event_base(state, payload), component=component or f"agent.{getattr(self, 'name', 'unknown')}")
        except Exception:
            return

    async def _emit_business_event(
        self,
        code: str,
        state: dict[str, Any],
        payload: dict[str, Any] | None = None,
        component: str | None = None,
    ) -> None:
        """Publica um evento de domínio pelo observer central do framework.

        O domínio apenas declara ``code``/``payload``; transporte, sequence e
        fan-out (Langfuse/PubSub/OCI Streaming/etc.) continuam no framework.
        """
        observer = getattr(self, "observer", None)
        if not observer or not code:
            return
        try:
            await observer.emit(
                str(code),
                self._event_base(state, payload),
                metadata={"business_event": True, "component": component or f"agent.{getattr(self, 'name', 'unknown')}"},
            )
        except Exception:
            return

    @staticmethod
    def _iter_business_events(value: Any):
        """Percorre envelopes MCP/workflow e encontra ``business_events``.

        Aceita string ou ``{code,payload,component}``. Duplicatas são eliminadas
        pelo chamador para impedir publicação repetida do mesmo efeito lógico.
        """
        if isinstance(value, dict):
            events = value.get("business_events")
            if isinstance(events, (list, tuple)):
                for event in events:
                    if isinstance(event, str):
                        yield {"code": event, "payload": {}, "component": None}
                    elif isinstance(event, dict) and event.get("code"):
                        yield {
                            "code": str(event.get("code")),
                            "payload": dict(event.get("payload") or {}),
                            "component": event.get("component"),
                        }
            for key, nested in value.items():
                if key != "business_events":
                    yield from AgentRuntimeMixin._iter_business_events(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                yield from AgentRuntimeMixin._iter_business_events(nested)

    async def _publish_business_events(self, result: dict[str, Any], state: dict[str, Any]) -> None:
        # Resultados de cache representam um efeito já executado e não podem
        # republicar eventos corporativos de negócio.
        if not isinstance(result, dict) or bool(result.get("cached")):
            return
        seen: set[str] = set()
        for event in self._iter_business_events(result):
            fingerprint = json.dumps(event, ensure_ascii=False, sort_keys=True, default=str)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            await self._emit_business_event(
                event["code"], state, event.get("payload") or {}, component=event.get("component")
            )

    # ------------------------------------------------------------------
    # RAG
    # ------------------------------------------------------------------
    @staticmethod
    def _iter_mapping_values(value: Any):
        if isinstance(value, Mapping):
            yield value
            for nested in value.values():
                yield from AgentRuntimeMixin._iter_mapping_values(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                yield from AgentRuntimeMixin._iter_mapping_values(nested)

    @classmethod
    def _mcp_rag_directive(cls, mcp_results: list[dict[str, Any]]) -> tuple[bool, str]:
        """Lê uma solicitação de RAG declarada pela tool/workflow de domínio.

        O domínio pode devolver ``requires_rag=true`` e opcionalmente
        ``rag_query``/``rag_queries``. A execução e a política de RAG continuam
        pertencendo ao framework; a tool apenas declara que evidência documental
        adicional é necessária para completar a resposta.
        """
        required = False
        queries: list[str] = []
        for item in mcp_results or []:
            if not isinstance(item, dict) or not item.get("ok"):
                continue
            for mapping in cls._iter_mapping_values(item.get("result")):
                if bool(mapping.get("requires_rag")):
                    required = True
                query = str(mapping.get("rag_query") or "").strip()
                if query:
                    queries.append(query)
                values = mapping.get("rag_queries")
                if isinstance(values, (list, tuple)):
                    queries.extend(str(v).strip() for v in values if str(v).strip())
        # Preserva ordem e remove duplicados sem normalizar a consulta do domínio.
        deduped = list(dict.fromkeys(queries))
        return required, "\n".join(deduped)

    @classmethod
    def _mcp_rag_sufficient(cls, mcp_results: list[dict[str, Any]]) -> bool:
        """Retorna True somente quando o domínio declara que MCP basta para este turno.

        Um tool result bem-sucedido não é, por si só, evidência de suficiência
        semântica. Para pular retrieval, a tool/workflow deve declarar
        ``rag_sufficient=true`` ou ``knowledge_sufficient=true`` em seu payload.
        Isso evita que o framework conheça nomes de tools ou termos de negócio.
        """
        for item in mcp_results or []:
            if not isinstance(item, dict) or not item.get("ok"):
                continue
            for mapping in cls._iter_mapping_values(item.get("result")):
                if bool(mapping.get("rag_sufficient")) or bool(mapping.get("knowledge_sufficient")):
                    return True
        return False


    @classmethod
    def _mcp_llm_composition_directive(cls, mcp_results: list[dict[str, Any]]) -> tuple[bool, list[str]]:
        """Lê instruções de composição declaradas por tools/workflows.

        O domínio pode devolver ``requires_llm_composition=true`` e uma
        ``response_instruction`` (ou ``response_instructions``). O framework
        continua responsável por executar o LLM; a tool apenas declara como a
        evidência operacional deve ser transformada em linguagem ao cliente.
        """
        required = False
        instructions: list[str] = []
        for item in mcp_results or []:
            if not isinstance(item, dict) or not item.get("ok"):
                continue
            for mapping in cls._iter_mapping_values(item.get("result")):
                if bool(mapping.get("requires_llm_composition")):
                    required = True
                instruction = str(mapping.get("response_instruction") or "").strip()
                if instruction:
                    instructions.append(instruction)
                values = mapping.get("response_instructions")
                if isinstance(values, (list, tuple)):
                    instructions.extend(str(v).strip() for v in values if str(v).strip())
        return required, list(dict.fromkeys(instructions))

    async def _retrieve_rag_context(self, state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        rag_service = getattr(self, "rag_service", None)
        settings = getattr(self, "settings", None)
        if not rag_service:
            return "", {
                "enabled": False,
                "attempted": False,
                "status": "no_service",
                "reason": "rag_service_not_configured",
                "provider": getattr(settings, "RAG_PROVIDER", "standard"),
            }
        mcp_results = state.get("mcp_results") or []
        requires_rag, rag_query_override = self._mcp_rag_directive(mcp_results)
        explicit_mcp_sufficient = self._mcp_rag_sufficient(mcp_results)
        if (
            not requires_rag
            and bool(getattr(settings, "SKIP_RAG_WHEN_MCP_SUFFICIENT", True))
            and explicit_mcp_sufficient
        ):
            return "", {
                "enabled": False,
                "skipped": True,
                "reason": "mcp_explicitly_sufficient",
                "required_by_tool": False,
                "mcp_explicitly_sufficient": True,
                "provider": getattr(settings, "RAG_PROVIDER", "standard"),
            }
        runtime = self.get_runtime_context(state)
        namespace = (
            (state.get("agent_profile") or {}).get("rag_namespace")
            or state.get("agent_id")
            or state.get("route")
            or "default"
        )
        graph_node = (
            runtime.context.get("graph_node")
            or runtime.business_context.get("customer_key")
            or runtime.business_context.get("contract_key")
            or runtime.context.get("customer_id")
        )
        settings = getattr(self, "settings", None)
        rewrite = bool(getattr(settings, "ENABLE_RAG_QUERY_REWRITE", False))
        rag_query = rag_query_override or runtime.sanitized_input
        try:
            result = await rag_service.retrieve(rag_query, namespace=namespace, graph_node=graph_node, rewrite=rewrite)
        except Exception as exc:
            # RAG é evidência auxiliar. Falha técnica não deve derrubar a jornada
            # conversacional inteira; o domínio/LLM pode continuar com as demais
            # evidências já disponíveis. Mantemos metadata estruturada para
            # observabilidade e para decisões posteriores.
            return "", {
                "enabled": False,
                "attempted": True,
                "failed": True,
                "technical_error": True,
                "technical_error_in_rag": True,
                "status": "error",
                "error": str(exc),
                "provider": getattr(settings, "RAG_PROVIDER", "standard"),
                "namespace": namespace,
                "query": rag_query,
                "query_overridden_by_tool": bool(rag_query_override),
                "required_by_tool": bool(requires_rag),
            }
        if bool(getattr(settings, "ENABLE_RAG_CONTEXT_COMPRESSION", False)) and hasattr(rag_service, "compress_context"):
            context = await rag_service.compress_context(result, question=runtime.sanitized_input)
        else:
            context = result.as_prompt_context()

        guardrail_pipeline = getattr(self, "guardrail_pipeline", None)
        retrieval_decisions: list[dict[str, Any]] = []
        if guardrail_pipeline is not None and context:
            guarded_context, decisions = await guardrail_pipeline.run_retrieval(
                context,
                {
                    "state": state,
                    "query": runtime.sanitized_input,
                    "namespace": namespace,
                    "rag_result": result,
                },
            )
            retrieval_decisions = [d.model_dump() if hasattr(d, "model_dump") else dict(d) for d in decisions]
            state.setdefault("guardrails", []).extend(retrieval_decisions)
            if any(not bool(getattr(d, "allowed", True)) for d in decisions):
                return "", {
                    "enabled": False,
                    "attempted": True,
                    "blocked": True,
                    "status": "blocked",
                    "reason": "retrieval_guardrail",
                    "provider": result.metadata.get("provider") or getattr(settings, "RAG_PROVIDER", "standard"),
                    "namespace": namespace,
                    "query": rag_query,
                    "document_count": len(result.documents),
                    "guardrails": retrieval_decisions,
                }
            context = guarded_context
        document_count = len(result.documents)
        provider = result.metadata.get("provider") or getattr(settings, "RAG_PROVIDER", "standard")
        status = "executed" if context and document_count else "empty"
        return context, {
            "enabled": True,
            "attempted": True,
            "status": status,
            "provider": provider,
            "namespace": namespace,
            "query": rag_query,
            "query_overridden_by_tool": bool(rag_query_override),
            "required_by_tool": bool(requires_rag),
            "mcp_explicitly_sufficient": explicit_mcp_sufficient,
            "latency_ms": result.latency_ms,
            "document_count": document_count,
            "graph_neighbors": len(result.graph_neighbors),
            "top_document_ids": [d.id for d in result.documents[:5]],
            "top_scores": [d.score for d in result.documents[:5]],
            "rewritten": result.metadata.get("rewritten"),
            "effective_query": result.query,
            "confidence": result.metadata.get("confidence"),
            "low_confidence": result.metadata.get("low_confidence"),
            "fallback_reason": result.metadata.get("fallback_reason"),
            "warnings": result.metadata.get("warnings") or [],
            "guardrails": retrieval_decisions,
        }

    # ------------------------------------------------------------------
    # MCP tools
    # ------------------------------------------------------------------
    def build_tool_arguments(
        self,
        state: dict[str, Any],
        *,
        tool_name: str | None = None,
        intent: str | None = None,
        aliases: dict[str, Iterable[str]] | None = None,
        extra_args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Monta argumentos canônicos para tools MCP.

        O mapper YAML continua sendo aplicado pelo MCPToolRouter. Este método só
        concentra a coleta de aliases, query, session e parâmetros explícitos.
        """
        runtime = self.get_runtime_context(state)
        args: dict[str, Any] = {
            "query": runtime.sanitized_input,
            "operator_instructions": runtime.sanitized_input,
        }
        args.update({k: v for k, v in runtime.tool_arguments.items() if v not in _EMPTY_VALUES})
        for canonical in ("customer_key", "contract_key", "interaction_key", "session_key"):
            value = runtime.pick(canonical)
            if value not in _EMPTY_VALUES:
                args[canonical] = value
        for canonical, names in (aliases or {}).items():
            value = runtime.pick(canonical, *list(names))
            if value not in _EMPTY_VALUES:
                args[canonical] = value
        if state.get("conversation_key") and "session_key" not in args:
            args["session_key"] = state.get("conversation_key")
        if intent:
            args.setdefault("intent", intent)
        if tool_name:
            args.setdefault("tool_name", tool_name)
        args.update({k: v for k, v in (extra_args or {}).items() if v not in _EMPTY_VALUES})
        return args

    @staticmethod
    def _coerce_extracted_value(value: Any, declared_type: str | None) -> Any:
        if value in _EMPTY_VALUES:
            return None
        kind = str(declared_type or "string").strip().lower()
        try:
            if kind in {"int", "integer"}:
                return int(value)
            if kind in {"float", "number"}:
                return float(value)
            if kind in {"bool", "boolean"}:
                if isinstance(value, bool):
                    return value
                normalized = str(value).strip().lower()
                if normalized in {"true", "1", "yes", "sim"}:
                    return True
                if normalized in {"false", "0", "no", "não", "nao"}:
                    return False
                return None
            return str(value).strip()
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _llm_response_text(response: Any) -> str:
        if response is None:
            return ""
        if isinstance(response, str):
            return response
        if isinstance(response, dict):
            return str(response.get("content") or response.get("text") or response.get("answer") or "")
        return str(getattr(response, "content", None) or getattr(response, "text", None) or response)

    def _drop_stale_message_extracted_arguments(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        explicit_fields: Iterable[str] = (),
    ) -> dict[str, Any]:
        """Remove valores herdados para campos cujo contrato diz ``from: message``.

        Em uma NOVA transação, ``context.tool_arguments`` pode ainda carregar
        parâmetros de uma operação anterior. Campos declarados pelo mapper como
        extraídos da mensagem corrente não podem nascer desse contexto antigo.
        Valores explicitamente extraídos deterministicamente do turno atual são
        preservados. Durante coleta incremental este helper não é usado.
        """
        router = getattr(self, "tool_router", None)
        if not router or not hasattr(router, "parameter_extract_rules"):
            return dict(arguments or {})
        rules = router.parameter_extract_rules(tool_name) or {}
        explicit = {str(name) for name in explicit_fields}
        cleaned = dict(arguments or {})
        for field_name, rule in rules.items():
            if (
                str(rule.get("from") or "message").lower() == "message"
                and str(field_name) not in explicit
            ):
                cleaned.pop(str(field_name), None)
        return cleaned

    async def _extract_mcp_parameters(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        state: dict[str, Any],
        *,
        overwrite_from_message: bool = False,
        exclude_fields: Iterable[str] = (),
    ) -> dict[str, Any]:
        """Executa regras ``extract`` declaradas para a tool escolhida.

        Precedência: argumento explícito > valor extraído > Business Context >
        default. A etapa é genérica: nomes e semântica vêm exclusivamente do
        mcp_parameter_mapping.yaml.
        """
        router = getattr(self, "tool_router", None)
        if not router or not hasattr(router, "parameter_extract_rules"):
            return dict(arguments or {})
        rules = router.parameter_extract_rules(tool_name) or {}
        if not rules:
            return dict(arguments or {})

        resolved = dict(arguments or {})
        excluded = {str(name) for name in (exclude_fields or ())}
        runtime = self.get_runtime_context(state)
        message = runtime.sanitized_input or runtime.original_text or runtime.user_text
        llm = getattr(self, "llm", None)

        for field_name, rule in rules.items():
            if str(field_name) in excluded:
                continue
            from_message = str(rule.get("from") or "message").lower() == "message"
            if not from_message:
                continue
            # Em uma nova transação, a mensagem atual prevalece para campos
            # declarados como ``from: message``. Durante COLLECTING_PARAMETERS
            # o default permanece False para congelar valores já coletados.
            if resolved.get(field_name) not in _EMPTY_VALUES and not overwrite_from_message:
                continue
            strategy = str(rule.get("strategy") or "llm").lower()
            value: Any = None

            if strategy in {"regex", "hybrid", "deterministic"}:
                pattern = str(rule.get("pattern") or "").strip()
                if pattern and message:
                    try:
                        match = re.search(pattern, str(message), flags=re.IGNORECASE)
                        if match:
                            group = int(rule.get("group", 1) or 1)
                            value = match.group(group)
                    except (re.error, IndexError, ValueError) as exc:
                        logger.warning(
                            "mcp.parameter.regex_extract_failed tool=%s field=%s error=%s",
                            tool_name, field_name, exc,
                        )
                if value is None and strategy == "hybrid":
                    strategy = "llm"
                elif value is None:
                    logger.info("mcp.parameter.regex_extracted_null tool=%s field=%s", tool_name, field_name)
                    continue

            if strategy == "month_name_pt":
                months = {
                    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3,
                    "abril": 4, "maio": 5, "junho": 6, "julho": 7,
                    "agosto": 8, "setembro": 9, "outubro": 10,
                    "novembro": 11, "dezembro": 12,
                }
                normalized = str(message or "").lower()
                value = next((number for name, number in months.items() if name in normalized), None)
            elif strategy == "llm":
                if llm is None or not message:
                    logger.warning(
                        "mcp.parameter.llm_extract_failed tool=%s field=%s error=llm_or_message_unavailable",
                        tool_name,
                        field_name,
                    )
                    continue
                description = str(rule.get("description") or f"Extraia o campo {field_name}.").strip()
                prompt = (
                    "Você é um extrator determinístico de parâmetros para uma tool MCP. "
                    "Responda somente JSON válido, sem markdown.\n"
                    f"Tool: {tool_name}\nCampo: {field_name}\nTipo: {rule.get('type', 'string')}\n"
                    f"Regra: {description}\nMensagem: {message}\n"
                    f"Formato obrigatório: {{\"{field_name}\": valor_ou_null}}"
                )
                try:
                    response = await llm.ainvoke(
                        [{"role": "user", "content": prompt}],
                        profile_name="mcp_parameter_extraction",
                        component_name="mcp_parameter_extraction",
                        generation_name="llm.mcp_parameter_extraction",
                        temperature=0.0,
                        max_tokens=80,
                    )
                    raw = self._llm_response_text(response).strip()
                    payload = parse_json_object(raw)
                    value = payload.get(field_name)
                except Exception as exc:
                    logger.warning(
                        "mcp.parameter.llm_extract_failed tool=%s field=%s error=%s",
                        tool_name,
                        field_name,
                        exc,
                    )
                    continue
            elif strategy not in {"regex", "hybrid", "deterministic", "month_name_pt"}:
                logger.warning(
                    "mcp.parameter.extract_strategy_unsupported tool=%s field=%s strategy=%s",
                    tool_name,
                    field_name,
                    strategy,
                )
                continue

            coerced = self._coerce_extracted_value(value, rule.get("type"))
            if coerced is None:
                logger.info("mcp.parameter.llm_extracted_null tool=%s field=%s", tool_name, field_name)
                continue
            resolved[field_name] = coerced
            logger.info(
                "mcp.parameter.llm_extracted tool=%s field=%s value=%s",
                tool_name,
                field_name,
                coerced,
            )
        return resolved

    def _tool_config(self, tool_name: str) -> Any:
        router = getattr(self, "tool_router", None)
        registry = getattr(router, "registry", None)
        if registry and hasattr(registry, "get_tool"):
            return registry.get_tool(tool_name)
        return None

    def _resolve_tool_execution_policy(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Resolve a política efetiva sem executar a tool."""
        router = getattr(self, "tool_router", None)
        if router and hasattr(router, "resolve_execution_policy"):
            return router.resolve_execution_policy(tool_name, arguments)
        if router and hasattr(router, "validate_execution_policy"):
            _allowed, _reason, metadata = router.validate_execution_policy(tool_name, arguments or {})
            return dict(metadata or {})
        cfg = self._tool_config(tool_name)
        tool_type = getattr(cfg, "tool_type", None) if cfg is not None else None
        return {
            "operation_type": "transactional" if tool_type in {"action", "transactional"} else "read_only",
            "require_confirmation": bool(getattr(cfg, "confirmation_required", False)) if cfg is not None else False,
            "policy_source": "tools.yaml",
        }

    async def _run_transaction_pre_validation(
        self,
        state: dict[str, Any],
        *,
        tool_name: str,
        arguments: dict[str, Any],
        policy: dict[str, Any],
        emit_events: bool = True,
    ) -> dict[str, Any] | None:
        """Execute an optional domain-owned MCP pre-validation before confirmation.

        The framework knows only the generic contract ``eligible``. Business rules
        remain in the configured MCP validator tool. No LLM is used here.
        """
        cfg = policy.get("pre_validation") if isinstance(policy, dict) else None
        if not isinstance(cfg, dict) or not cfg.get("enabled"):
            return None
        validator = str(cfg.get("tool") or "").strip()
        if not validator:
            return None
        validation_args = dict(arguments or {})
        validation_args.pop("confirmed", None)
        validation_args["target_tool"] = tool_name
        if emit_events:
            await self._emit_ic(
                "IC.TRANSACTION_PREVALIDATION_REQUESTED",
                state,
                {"tool_name": tool_name, "validator_tool": validator},
                component="agent_runtime.tool_policy",
            )
        result = await self._call_mcp_tool(validator, validation_args, state)
        payload = result.get("result") if isinstance(result, dict) and isinstance(result.get("result"), dict) else result
        eligible = payload.get("eligible") if isinstance(payload, dict) else None
        if eligible is True:
            state["transaction_pre_validation"] = {
                "tool_name": tool_name, "validator_tool": validator, "eligible": True, "result": result
            }
            if emit_events:
                await self._emit_ic(
                    "IC.TRANSACTION_PREVALIDATION_PASSED", state,
                    {"tool_name": tool_name, "validator_tool": validator},
                    component="agent_runtime.tool_policy",
                )
            return None
        transport_failed = isinstance(result, dict) and result.get("ok") is False and eligible is None
        if transport_failed and bool(cfg.get("fail_open")):
            return None
        status = str((payload or {}).get("status") or ("PREVALIDATION_ERROR" if transport_failed else "OUT_OF_SCOPE"))
        state["transaction_pre_validation"] = {
            "tool_name": tool_name,
            "validator_tool": validator,
            "eligible": False,
            "status": status,
            "error": (payload or {}).get("error") if isinstance(payload, dict) else None,
            "terminal": True,
            "result": result,
        }
        # A rejeição da pré-validação encerra o latch transacional imediatamente.
        # A regra de negócio permanece no MCP; o framework apenas materializa o
        # resultado genérico de elegibilidade e garante que o próximo turno volte
        # ao roteamento normal, sem herdar COLLECTING_/WAITING_.
        self._finish_active_transaction(state, "OUT_OF_SCOPE", result=result)
        state["next_state"] = None
        state["confirmation_required"] = False
        state["confirmation_received"] = False
        if emit_events:
            await self._emit_ic(
                "IC.TRANSACTION_PREVALIDATION_REJECTED", state,
                {"tool_name": tool_name, "validator_tool": validator, "status": status, "error": (payload or {}).get("error")},
                component="agent_runtime.tool_policy",
            )
        enriched = dict(result or {})
        enriched["pre_validation"] = True
        enriched["target_tool"] = tool_name
        enriched["transaction_status"] = "OUT_OF_SCOPE"
        return enriched

    def _validate_tool_execution_policy(self, tool_name: str, arguments: dict[str, Any]) -> tuple[bool, str | None]:
        """Aplica a mesma política central usada pelo MCPToolRouter."""
        router = getattr(self, "tool_router", None)
        if router and hasattr(router, "validate_execution_policy"):
            allowed, reason, _metadata = router.validate_execution_policy(tool_name, arguments)
            return allowed, reason
        cfg = self._tool_config(tool_name)
        required: list[str] = []
        tool_type = None
        confirmation_required = False
        if cfg is not None:
            tool_type = getattr(cfg, "tool_type", None) or getattr(cfg, "type", None)
            confirmation_required = bool(getattr(cfg, "confirmation_required", False))
            required = list(getattr(cfg, "requires", None) or [])
            execution_policy = getattr(cfg, "execution_policy", None) or {}
            if isinstance(execution_policy, dict):
                required.extend(execution_policy.get("requires") or [])
                confirmation_required = confirmation_required or bool(execution_policy.get("confirmation_required"))
        for field_name in required:
            if arguments.get(field_name) in _EMPTY_VALUES:
                return False, f"Campo obrigatório ausente para execução da tool: {field_name}"
        if confirmation_required and not (arguments.get("confirmed") or arguments.get("confirmation") is True):
            return False, "Tool exige confirmação explícita antes da execução"
        return True, None

    def _mcp_cache_enabled(self) -> bool:
        """Retorna se o cache MCP está habilitado globalmente.

        A chave global fica no .env/settings. A decisão por tool fica em
        config/tools.yaml, dentro do próprio cadastro da tool.
        """
        settings = getattr(self, "settings", None)
        return bool(getattr(settings, "ENABLE_MCP_CACHE", True))

    def _mcp_tool_cache_config(self, tool_name: str) -> dict[str, Any]:
        """Lê a política de cache diretamente da tool em tools.yaml.

        Estrutura esperada no catálogo atual:

        tools:
          consultar_fatura:
            description: ...
            mcp_server: telecom
            enabled: true
            cache:
              enabled: true
              ttl_seconds: 600
            args_schema:
              msisdn: string

        Compatibilidade mantida:
        - cache: true|false
        - cache.enabled
        - cache.ttl_seconds
        - cache.ttl
        - cache_ttl_seconds
        - execution_policy.cache/cacheable/cache_ttl_seconds

        Por segurança, o default é NÃO cachear.
        """
        cfg = self._tool_config(tool_name)
        if cfg is None:
            return {}

        raw_cache = getattr(cfg, "cache", None) or {}
        policy: dict[str, Any] = {}

        if isinstance(raw_cache, bool):
            policy["enabled"] = raw_cache
        elif isinstance(raw_cache, dict):
            policy.update(raw_cache)

        # Compatibilidade com campos antigos/compactos, sem mudar o tools.yaml atual.
        execution_policy = getattr(cfg, "execution_policy", None) or {}
        if isinstance(execution_policy, dict):
            if "cache" in execution_policy and "enabled" not in policy:
                policy["enabled"] = execution_policy.get("cache")
            if "cacheable" in execution_policy and "enabled" not in policy:
                policy["enabled"] = execution_policy.get("cacheable")
            if "cache_ttl_seconds" in execution_policy and "ttl_seconds" not in policy:
                policy["ttl_seconds"] = execution_policy.get("cache_ttl_seconds")

        if "cache_ttl_seconds" in policy and "ttl_seconds" not in policy:
            policy["ttl_seconds"] = policy.get("cache_ttl_seconds")
        if "ttl" in policy and "ttl_seconds" not in policy:
            policy["ttl_seconds"] = policy.get("ttl")

        return policy

    def _mcp_cache_policy(self, tool_name: str) -> dict[str, Any]:
        """Resolve a política final de cache da tool MCP.

        Fonte da verdade: config/tools.yaml, no bloco `cache` da própria tool.
        Não existe regra por prefixo, idioma ou nome da ferramenta.

        A chave de cache é baseada em:
        - tool_name
        - campos declarados em args_schema da tool em config/tools.yaml.

        Não entram na chave: session_id, request_id, trace_id, timestamp, intent,
        agent_id, business_context completo ou atributos auxiliares fora do
        args_schema, pois esses valores tendem a mudar entre chamadas e
        impediriam cache HIT.
        """
        settings = getattr(self, "settings", None)
        default_ttl = int(
            getattr(settings, "MCP_CACHE_TTL_SECONDS", None)
            or getattr(settings, "CACHE_TTL_SECONDS", 300)
            or 300
        )
        raw = self._mcp_tool_cache_config(tool_name)

        enabled = bool(raw.get("enabled", False)) if isinstance(raw, dict) else False
        ttl_seconds = raw.get("ttl_seconds", default_ttl) if isinstance(raw, dict) else default_ttl
        try:
            ttl_seconds = int(ttl_seconds or default_ttl)
        except Exception:
            ttl_seconds = default_ttl

        return {
            "enabled": enabled,
            "cacheable": enabled,
            "ttl_seconds": ttl_seconds,
        }

    def _mcp_cache_ttl_seconds(self, tool_name: str | None = None) -> int:
        if tool_name:
            return int(self._mcp_cache_policy(tool_name).get("ttl_seconds") or 300)
        settings = getattr(self, "settings", None)
        return int(
            getattr(settings, "MCP_CACHE_TTL_SECONDS", None)
            or getattr(settings, "CACHE_TTL_SECONDS", 300)
            or 300
        )

    def _is_mcp_tool_cacheable(self, tool_name: str, arguments: dict[str, Any]) -> bool:
        """Define se uma tool MCP pode ser cacheada com segurança.

        A decisão vem exclusivamente de config/tools.yaml:

        cache:
          enabled: true
          ttl_seconds: 600
        """
        if not self._mcp_cache_enabled():
            return False
        policy = self._mcp_cache_policy(tool_name)
        return bool(policy.get("enabled", False) and policy.get("cacheable", False))

    def _normalize_mcp_cache_value(self, value: Any) -> Any:
        """Normaliza valores para gerar uma cache key estável.

        Remove variações acidentais, como espaços em strings, e ordena estruturas
        aninhadas. Isso evita MISS quando a semântica da chamada é a mesma.
        """
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            return {
                str(k): self._normalize_mcp_cache_value(v)
                for k, v in sorted(value.items(), key=lambda item: str(item[0]))
                if v not in _EMPTY_VALUES
            }
        if isinstance(value, (list, tuple)):
            return [self._normalize_mcp_cache_value(v) for v in value if v not in _EMPTY_VALUES]
        return value

    def _mcp_cache_args_schema_fields(self, tool_name: str) -> list[str]:
        """Retorna os campos declarados no args_schema da tool.

        Fonte da verdade: config/tools.yaml.
        Somente esses campos entram na cache_key, porque eles representam o
        contrato público/funcional da chamada MCP. Campos auxiliares que possam
        aparecer no payload em tempo de execução não devem quebrar o cache.
        """
        cfg = self._tool_config(tool_name)
        schema = getattr(cfg, "args_schema", None) if cfg is not None else None
        if isinstance(schema, dict):
            return [str(k) for k in schema.keys()]
        return []

    def _mcp_cache_key_payload(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Monta o payload determinístico usado na chave de cache MCP.

        Regra principal:
        mesma tool + mesmos campos de args_schema + mesmos valores = mesma chave.

        A chave NÃO usa session_id, request_id, trace_id, timestamp, intent,
        business_context completo ou qualquer atributo auxiliar fora do
        args_schema da tool. Isso evita MISS permanente por dados voláteis.
        """
        args = arguments or {}
        schema_fields = self._mcp_cache_args_schema_fields(tool_name)

        if schema_fields:
            key_arguments = {
                field: args.get(field)
                for field in schema_fields
                if args.get(field) not in _EMPTY_VALUES
            }
        else:
            # Fallback defensivo para tools antigas sem args_schema.
            key_arguments = {
                str(k): v
                for k, v in args.items()
                if v not in _EMPTY_VALUES
            }

        return {
            "tool_name": tool_name,
            "args_schema_fields": schema_fields,
            "arguments": self._normalize_mcp_cache_value(key_arguments),
        }

    def _mcp_cache_key(self, tool_name: str, arguments: dict[str, Any], state: dict[str, Any] | None = None) -> str:
        payload = self._mcp_cache_key_payload(tool_name, arguments)
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return "mcp:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _prepare_mcp_call(self, tool_name: str, arguments: dict[str, Any], state: dict[str, Any]):
        """Resolve servidor e argumentos efetivos antes de executar o MCP.

        Importante para cache:
        - build_tool_arguments() ainda contém campos canônicos/auxiliares;
        - MCPToolRouter aplica mcp_parameter_mapping.yaml;
        - a cache_key deve usar os argumentos finais enviados ao MCP, filtrados
          pelo args_schema da tool.
        """
        router = getattr(self, "tool_router", None)
        if not router:
            return None, {}, {"ok": False, "tool_name": tool_name, "error": "MCP Tool Router indisponível"}

        runtime = self.get_runtime_context(state)
        if hasattr(router, "prepare_call"):
            server, mapped_arguments, error = router.prepare_call(
                tool_name,
                arguments,
                business_context=runtime.business_context,
                original_context=runtime.as_original_context(),
            )
            if error is not None:
                result = error.model_dump(mode="json") if hasattr(error, "model_dump") else dict(error)
                return None, {}, result
            return server, mapped_arguments, None

        # Compatibilidade com versões antigas do router.
        return None, arguments or {}, None

    async def _call_mcp_tool_uncached(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        state: dict[str, Any],
        *,
        prepared_server: Any | None = None,
        mapped_arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        router = getattr(self, "tool_router", None)
        if not router:
            return {"ok": False, "tool_name": tool_name, "error": "MCP Tool Router indisponível"}

        effective_arguments = mapped_arguments if mapped_arguments is not None else arguments
        await self._emit_ic(
            "IC.MCP_TOOL_EXECUTING",
            state,
            {"tool_name": tool_name, "arguments": self._normalize_mcp_cache_value(effective_arguments or {})},
            component="agent_runtime.mcp",
        )

        if prepared_server is not None and mapped_arguments is not None and hasattr(router, "call_prepared"):
            res = await router.call_prepared(tool_name, prepared_server, mapped_arguments)
        else:
            runtime = self.get_runtime_context(state)
            res = await router.call(
                tool_name,
                arguments,
                business_context=runtime.business_context,
                original_context=runtime.as_original_context(),
            )
        result = res.model_dump(mode="json") if hasattr(res, "model_dump") else dict(res)
        if isinstance(result, dict):
            result.setdefault("cached", False)
        await self._emit_ic(
            "IC.MCP_TOOL_EXECUTED",
            state,
            {
                "tool_name": tool_name,
                "ok": result.get("ok") if isinstance(result, dict) else None,
                "server_name": result.get("server_name") if isinstance(result, dict) else None,
                "error": result.get("error") if isinstance(result, dict) else None,
            },
            component="agent_runtime.mcp",
        )
        await self._publish_business_events(result, state)
        return result

    async def _call_mcp_tool(self, tool_name: str, arguments: dict[str, Any] | None, state: dict[str, Any]) -> dict[str, Any]:
        args = await self._extract_mcp_parameters(tool_name, dict(arguments or {}), state)
        telemetry = getattr(self, "telemetry", None)

        prepared_server, effective_args, prepare_error = self._prepare_mcp_call(tool_name, args, state)
        if prepare_error is not None:
            await self._emit_ic(
                "IC.MCP_TOOL_PREPARE_FAILED",
                state,
                {"tool_name": tool_name, "error": prepare_error.get("error")},
                component="agent_runtime.mcp",
            )
            return prepare_error

        guardrail_pipeline = getattr(self, "guardrail_pipeline", None)
        if guardrail_pipeline is not None:
            _, decisions = await guardrail_pipeline.run_tool(
                tool_name,
                effective_args,
                {"state": state, "intent": state.get("intent"), "route": state.get("route")},
            )
            serialized = [d.model_dump() if hasattr(d, "model_dump") else dict(d) for d in decisions]
            state.setdefault("guardrails", []).extend(serialized)
            blocked = next((d for d in decisions if not bool(getattr(d, "allowed", True))), None)
            if blocked is not None:
                reason = getattr(blocked, "reason", None) or "Tool bloqueada por guardrail"
                await self._emit_grl(
                    getattr(blocked, "code", "TOOL_VAL"),
                    state,
                    {"tool_name": tool_name, "reason": reason},
                    component="agent_runtime.tool_guardrail",
                )
                return {
                    "ok": False,
                    "tool_name": tool_name,
                    "skipped": True,
                    "guardrail_blocked": True,
                    "error": reason,
                    "guardrails": serialized,
                }

        # A política de cache continua vindo do tools.yaml. A chave, porém, usa
        # os argumentos EFETIVOS do MCP, ou seja, depois do mcp_parameter_mapping.
        cacheable = self._is_mcp_tool_cacheable(tool_name, effective_args) and getattr(self, "cache", None) is not None

        if not cacheable:
            logger.info("MCP cache bypass", extra={"tool_name": tool_name, "reason": "disabled_or_not_configured"})
            await self._emit_ic(
                "IC.MCP_CACHE_BYPASS",
                state,
                {"tool_name": tool_name, "reason": "disabled_or_not_configured"},
                component="agent_runtime.mcp_cache",
            )
            return await self._call_mcp_tool_uncached(
                tool_name,
                args,
                state,
                prepared_server=prepared_server,
                mapped_arguments=effective_args,
            )

        key = self._mcp_cache_key(tool_name, effective_args, state)
        key_payload = self._mcp_cache_key_payload(tool_name, effective_args)

        # Deduplicação intra-turno: se o mesmo fluxo tentar chamar a mesma tool
        # duas vezes com os mesmos argumentos no mesmo state, reaproveita o
        # primeiro resultado e impede segunda chamada HTTP ao MCP Server.
        turn_cache = state.setdefault("_mcp_tool_results_by_cache_key", {})
        if key in turn_cache:
            deduped = dict(turn_cache[key]) if isinstance(turn_cache[key], dict) else turn_cache[key]
            if isinstance(deduped, dict):
                deduped.setdefault("cached", True)
                deduped["deduped"] = True
                deduped.setdefault("cache_key", key)
            logger.info("MCP tool deduped in turn", extra={"tool_name": tool_name, "cache_key": key})
            await self._emit_ic(
                "IC.MCP_TOOL_DEDUPED",
                state,
                {"tool_name": tool_name, "cache_key": key, "cache_key_payload": key_payload},
                component="agent_runtime.mcp_cache",
            )
            return deduped

        cached = await self._cache_get(key)
        if cached is not None:
            logger.info("MCP cache hit", extra={"tool_name": tool_name, "cache_key": key, "cache_key_payload": key_payload})
            if telemetry:
                await telemetry.event("cache.mcp.hit", {"tool_name": tool_name, "key": key}, kind="cache")
            await self._emit_ic(
                "IC.MCP_CACHE_HIT",
                state,
                {"tool_name": tool_name, "cache_key": key, "cache_key_payload": key_payload},
                component="agent_runtime.mcp_cache",
            )
            if isinstance(cached, dict):
                cached.setdefault("cached", True)
                cached.setdefault("cache_key", key)
            turn_cache[key] = cached
            return cached

        logger.info("MCP cache miss", extra={"tool_name": tool_name, "cache_key": key, "cache_key_payload": key_payload})
        if telemetry:
            await telemetry.event("cache.mcp.miss", {"tool_name": tool_name, "key": key}, kind="cache")
        await self._emit_ic(
            "IC.MCP_CACHE_MISS",
            state,
            {"tool_name": tool_name, "cache_key": key, "cache_key_payload": key_payload},
            component="agent_runtime.mcp_cache",
        )

        result = await self._call_mcp_tool_uncached(
            tool_name,
            args,
            state,
            prepared_server=prepared_server,
            mapped_arguments=effective_args,
        )
        if isinstance(result, dict):
            result.setdefault("cache_key", key)
        turn_cache[key] = result

        # Cacheia apenas respostas bem-sucedidas. Erros permanecem visíveis e
        # permitem nova tentativa na próxima interação.
        if result.get("ok"):
            ttl = self._mcp_cache_ttl_seconds(tool_name)
            await self._cache_set(key, result, ttl)
            logger.info("MCP cache set", extra={"tool_name": tool_name, "cache_key": key, "ttl_seconds": ttl, "cache_key_payload": key_payload})
            if telemetry:
                await telemetry.event("cache.mcp.set", {"tool_name": tool_name, "key": key, "ttl_seconds": ttl}, kind="cache")
            await self._emit_ic(
                "IC.MCP_CACHE_SET",
                state,
                {"tool_name": tool_name, "cache_key": key, "ttl_seconds": ttl, "cache_key_payload": key_payload},
                component="agent_runtime.mcp_cache",
            )
        else:
            logger.info("MCP cache not stored", extra={"tool_name": tool_name, "cache_key": key, "reason": "tool_result_not_ok", "cache_key_payload": key_payload})
            await self._emit_ic(
                "IC.MCP_CACHE_NOT_STORED",
                state,
                {"tool_name": tool_name, "cache_key": key, "reason": "tool_result_not_ok", "cache_key_payload": key_payload},
                component="agent_runtime.mcp_cache",
            )
        return result

    @staticmethod
    def _confirmation_decision(text: str) -> str | None:
        return parse_transaction_confirmation(text)

    def _transaction_parameter_schema(self, tool_name: str, policy: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return schema metadata for transactional required parameters.

        Backward compatibility is intentional:
        - legacy ``args_schema: {field: string}`` remains valid;
        - enriched ``args_schema`` entries may provide ``type``/``description``;
        - when a legacy entry has no description, a declarative description from
          ``mcp_parameter_mapping.yaml`` is used when available.

        The framework never assigns domain meaning to a parameter name.  It only
        forwards metadata declared by the agent so the generic LLM extractor can
        interpret the user's wording more accurately.
        """
        cfg = self._tool_config(tool_name)
        raw_schema = dict(getattr(cfg, "args_schema", {}) or {}) if cfg is not None else {}
        required = [str(name) for name in ((policy or {}).get("requires") or getattr(cfg, "requires", []) or [])]

        # Optional semantic metadata already declared by the agent for MCP
        # extraction.  This is only a fallback; args_schema remains authoritative.
        extract_rules: dict[str, dict[str, Any]] = {}
        router = getattr(self, "tool_router", None)
        if router is not None and hasattr(router, "parameter_extract_rules"):
            try:
                extract_rules = dict(router.parameter_extract_rules(tool_name) or {})
            except Exception:
                # Schema construction must never break legacy agents merely
                # because optional descriptive metadata cannot be loaded.
                extract_rules = {}

        names = required or [str(name) for name in raw_schema.keys()]
        normalized: dict[str, Any] = {}
        for name in names:
            raw = raw_schema.get(name, "string")
            rule = extract_rules.get(name) if isinstance(extract_rules.get(name), dict) else {}
            fallback_description = str((rule or {}).get("description") or "").strip() or None

            if isinstance(raw, dict):
                entry = dict(raw)
                entry.setdefault("type", "string")
                if not entry.get("description") and fallback_description:
                    entry["description"] = fallback_description
                normalized[name] = entry
            elif fallback_description:
                normalized[name] = {
                    "type": raw or "string",
                    "description": fallback_description,
                }
            else:
                # Preserve the exact legacy representation when there is no
                # additional metadata to contribute.
                normalized[name] = raw or "string"

        return normalized

    def _transaction_tool_description(self, tool_name: str) -> str:
        cfg = self._tool_config(tool_name)
        return str(getattr(cfg, "description", "") or "") if cfg is not None else ""

    async def _extract_transaction_parameters(
        self,
        state: dict[str, Any],
        *,
        tool_name: str,
        missing_parameters: list[str],
        known_arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Use the dedicated LLM extractor for pending transaction parameters.

        A route decision may already contain the extraction performed by the
        router solely to enforce parameter-before-intent-shift precedence.  Reuse
        it to avoid a second LLM call in the same turn.
        """
        route_meta = ((state.get("route_decision") or {}).get("metadata") or {}) if isinstance(state.get("route_decision"), dict) else {}
        cached = route_meta.get("transaction_parameter_values")
        if isinstance(cached, dict):
            allowed = set(str(x) for x in missing_parameters)
            reused = {str(k): v for k, v in cached.items() if str(k) in allowed and v not in _EMPTY_VALUES}
            if reused:
                return reused

        active = self._active_transaction(state) or {}
        schema = active.get("parameter_schema") if isinstance(active.get("parameter_schema"), dict) else None
        if not schema:
            policy = self._resolve_tool_execution_policy(tool_name, known_arguments or {})
            schema = self._transaction_parameter_schema(tool_name, policy)
        description = str(active.get("tool_description") or self._transaction_tool_description(tool_name) or "")
        text = state.get("sanitized_input") or state.get("user_text") or ""
        return await extract_transaction_parameters(
            getattr(self, "llm", None),
            text=str(text),
            tool_name=tool_name,
            missing_parameters=list(missing_parameters or []),
            known_arguments=known_arguments or {},
            parameter_schema=schema,
            tool_description=description,
        )

    def _transactional_action_match(self, text: str, tools: list[str] | None = None) -> str | None:
        """Detecta solicitação transacional usando metadados de tools.yaml.

        Quando ``tools`` é None, examina todas as tools registradas. Isso permite
        bloquear uma resposta direta read-only mesmo quando a intent atual ainda
        não expôs a action tool correta.
        """
        normalized = (text or "").lower()
        router = getattr(self, "tool_router", None)
        registry = getattr(router, "registry", None)
        names = list(tools or (list(getattr(registry, "tools", {}).keys()) if registry else []))
        for tool in names:
            if self._resolve_tool_execution_policy(tool).get("operation_type") != "transactional":
                continue
            cfg = registry.get_tool(tool) if registry else None
            keywords = list(getattr(cfg, "selection_keywords", None) or [])
            if any(str(token).lower() in normalized for token in keywords):
                return tool
        return None

    def _select_transactional_tool(self, tools: list[str], text: str) -> str | None:
        matched = self._transactional_action_match(text, tools)
        if matched:
            return matched

        # Generic fallback: once routing has constrained the allowlist, a single
        # transactional capability is unambiguous even when the user's wording
        # does not contain one of the tool-specific selection keywords.
        transactional = [
            tool
            for tool in tools
            if self._resolve_tool_execution_policy(tool).get("operation_type") == "transactional"
        ]
        return transactional[0] if len(transactional) == 1 else None

    @staticmethod
    def _agent_state_prefix(agent_name: str | None) -> str:
        raw = str(agent_name or "support_agent").strip().upper()
        raw = re.sub(r"_AGENT$", "", raw)
        raw = re.sub(r"[^A-Z0-9]+", "_", raw).strip("_") or "SUPPORT"
        return raw

    def _collecting_state_name(self, state: dict[str, Any]) -> str:
        current = state.get("route") or state.get("active_agent") or getattr(self, "name", None)
        return f"COLLECTING_{self._agent_state_prefix(current)}_PARAMETERS"

    def _waiting_state_name(self, state: dict[str, Any]) -> str:
        current = state.get("route") or state.get("active_agent") or getattr(self, "name", None)
        return f"WAITING_{self._agent_state_prefix(current)}_CONFIRMATION"

    @staticmethod
    def _workflow_resume_decision(text: str, pending: dict[str, Any] | None = None) -> str:
        # Prefer the workflow's declarative input contract. This removes domain
        # semantics from the framework: SIM/NAO, numeric choices or free text are
        # interpreted only from ``expected_input`` persisted by the paused flow.
        pause = (pending or {}).get("pause") if isinstance(pending, dict) else None
        expected = pause.get("expected_input") if isinstance(pause, dict) else None
        matched = match_expected_input(text, expected)
        if matched is not None:
            return matched

        # Backward compatibility for old checkpoints that predate expected_input.
        # This branch is intentionally limited to the previous generic yes/no
        # behavior and is not used when the workflow provides a contract.
        if isinstance(expected, dict):
            return "OUTRO"
        normalized = " ".join((text or "").strip().lower().split())
        normalized = re.sub(r"[.!?]+$", "", normalized).strip()
        yes = {"sim", "s", "claro", "isso", "correto", "pode", "pode sim", "entendi", "conseguiu", "resolveu"}
        no = {"não", "nao", "n", "não resolveu", "nao resolveu", "não entendi", "nao entendi", "negativo"}
        if normalized in yes or normalized.startswith("sim "):
            return "SIM"
        if normalized in no or normalized.startswith("não ") or normalized.startswith("nao "):
            return "NAO"
        return "OUTRO"

    @staticmethod
    def _workflow_pause_descriptor(workflow: dict[str, Any]) -> dict[str, Any]:
        """Recover the complete pause descriptor from a workflow result.

        Runtime v2 exposes ``pause`` as a compact public summary, while the
        LangGraph interrupt carries ``expected_input`` and ``resume_from``. Keep
        both forms compatible without coupling this logic to a domain workflow.
        """
        descriptor = dict(workflow.get("pause") or {}) if isinstance(workflow.get("pause"), dict) else {}
        state = workflow.get("state") if isinstance(workflow.get("state"), dict) else {}
        interrupts = state.get("__interrupt__") if isinstance(state, dict) else None
        if isinstance(interrupts, list) and interrupts:
            first = interrupts[0]
            value = first.get("value") if isinstance(first, dict) else None
            if isinstance(value, dict):
                for key, item in value.items():
                    descriptor.setdefault(key, item)
        return descriptor

    @staticmethod
    def _workflow_payload_from_tool_result(result: dict[str, Any]) -> dict[str, Any] | None:
        data = result.get("result") if isinstance(result, dict) else None
        if not isinstance(data, dict):
            return None
        # MCP HTTP envelope may contain another result layer.
        nested = data.get("result")
        if isinstance(nested, dict) and nested.get("status") in {"PAUSED", "COMPLETED", "FAILED"}:
            return nested
        if data.get("status") in {"PAUSED", "COMPLETED", "FAILED"}:
            return data
        return None

    def _capture_pending_domain_workflow(self, state: dict[str, Any], tool_result: dict[str, Any]) -> None:
        workflow = self._workflow_payload_from_tool_result(tool_result)
        if not workflow:
            return
        metadata = workflow.get("metadata") if isinstance(workflow.get("metadata"), dict) else {}
        workflow_name = str(metadata.get("workflow_name") or workflow.get("workflow_name") or "").strip()
        if workflow_name and workflow.get("status") in {"PAUSED", "COMPLETED"}:
            executed = [str(x) for x in (state.get("business_workflows_executed") or []) if str(x).strip()]
            if workflow_name not in executed:
                executed.append(workflow_name)
            state["business_workflows_executed"] = executed
        if workflow.get("status") != "PAUSED":
            # Clearing must be materialized in the graph-state patch. ``pop``/absence
            # is not enough with LangGraph state merging: an older latch can survive
            # into the next turn and incorrectly resume a workflow that already
            # completed. Only clear the currently owned execution (or an unlabeled
            # legacy latch); never clear a different concurrently tracked workflow.
            pending = state.get("pending_domain_workflow")
            pending_execution = (pending or {}).get("execution_id") if isinstance(pending, dict) else None
            workflow_execution = metadata.get("workflow_execution_id") or workflow.get("execution_id")
            if not pending_execution or not workflow_execution or str(pending_execution) == str(workflow_execution):
                state["pending_domain_workflow"] = None
                if state.get("transaction_status") == "WORKFLOW_PAUSED":
                    state["transaction_status"] = None
            return
        state["pending_domain_workflow"] = {
            "workflow_name": metadata.get("workflow_name") or workflow.get("workflow_name"),
            "execution_id": metadata.get("workflow_execution_id") or workflow.get("execution_id"),
            "resume_tool": metadata.get("resume_tool") or "retomar_workflow",
            "owner_agent": state.get("active_agent") or state.get("route"),
            "owner_intent": state.get("intent"),
            "pause": self._workflow_pause_descriptor(workflow),
        }
        state["transaction_status"] = "WORKFLOW_PAUSED"

    async def _resume_pending_domain_workflow(self, state: dict[str, Any], text: str) -> dict[str, Any] | None:
        pending = state.get("pending_domain_workflow")
        if not isinstance(pending, dict) or not pending.get("execution_id"):
            return None
        tool_name = str(pending.get("resume_tool") or "retomar_workflow")
        arguments = {
            "workflow_name": pending.get("workflow_name"),
            "execution_id": pending.get("execution_id"),
            "resposta_usuario": self._workflow_resume_decision(text, pending),
        }
        result = await self._call_mcp_tool(tool_name, arguments, state)
        workflow = self._workflow_payload_from_tool_result(result)
        self._capture_pending_domain_workflow(state, result)
        if workflow and workflow.get("status") == "PAUSED":
            pass
        else:
            # Explicit tombstone: transaction_state_patch() must carry the clear
            # through LangGraph's state merge. Removing the key locally would let
            # the previous PAUSED latch remain durable in the graph state.
            state["pending_domain_workflow"] = None
            if state.get("transaction_status") == "WORKFLOW_PAUSED":
                state["transaction_status"] = None
        return result


    @staticmethod
    def _tool_clarification_payload_from_result(result: dict[str, Any]) -> dict[str, Any] | None:
        data = result.get("result") if isinstance(result, dict) else None
        if not isinstance(data, dict):
            return None
        nested = data.get("result")
        if isinstance(nested, dict) and nested.get("status") == "NEEDS_CLARIFICATION":
            data = nested
        if data.get("status") != "NEEDS_CLARIFICATION":
            return None
        return data

    def _capture_pending_tool_clarification(
        self,
        state: dict[str, Any],
        tool_result: dict[str, Any],
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> None:
        payload = self._tool_clarification_payload_from_result(tool_result)
        if not payload:
            return
        options = payload.get("options") if isinstance(payload.get("options"), list) else []
        state["pending_tool_clarification"] = {
            "tool_name": tool_name,
            "arguments": dict(arguments or {}),
            "parameter": str(payload.get("parameter") or "subject"),
            "question": str(payload.get("question") or "Qual opção você quis dizer?"),
            "options": [dict(x) for x in options if isinstance(x, dict)],
        }
        state["transaction_status"] = "TOOL_RESULT_CLARIFICATION"

    @staticmethod
    def _choose_tool_clarification_option(text: str, options: list[dict[str, Any]]) -> dict[str, Any] | None:
        normalized = " ".join(str(text or "").strip().lower().split())
        if not normalized:
            return None
        number = re.fullmatch(r"(?:op[cç][aã]o\s*)?(\d+)", normalized)
        if number:
            idx = int(number.group(1)) - 1
            if 0 <= idx < len(options):
                return options[idx]
        for option in options:
            label = str(option.get("label") or option.get("value") or "").strip().lower()
            value = str(option.get("value") or option.get("label") or "").strip().lower()
            if normalized in {label, value} or (label and label in normalized) or (value and value in normalized):
                return option
        return None

    async def _resume_pending_tool_clarification(self, state: dict[str, Any], text: str) -> dict[str, Any] | None:
        pending = state.get("pending_tool_clarification")
        if not isinstance(pending, dict):
            return None
        options = pending.get("options") if isinstance(pending.get("options"), list) else []
        selected = self._choose_tool_clarification_option(text, options)
        if selected is None:
            return {
                "ok": True,
                "executed": False,
                "tool_name": pending.get("tool_name"),
                "needs_clarification": True,
                "question": pending.get("question"),
                "options": options,
            }
        tool_name = str(pending.get("tool_name") or "")
        arguments = dict(pending.get("arguments") or {})
        parameter = str(pending.get("parameter") or "subject")
        arguments[parameter] = selected.get("value") if selected.get("value") not in (None, "") else selected.get("label")
        arguments["clarification_resolved"] = True
        state.pop("pending_tool_clarification", None)
        result = await self._call_mcp_tool(tool_name, arguments, state)
        self._capture_pending_domain_workflow(state, result)
        self._capture_pending_tool_clarification(state, result, tool_name=tool_name, arguments=arguments)
        if not state.get("pending_domain_workflow") and not state.get("pending_tool_clarification"):
            state["transaction_status"] = "COMPLETED" if result.get("ok") else "FAILED"
        return result

    @staticmethod
    def _transaction_is_active(state: dict[str, Any]) -> bool:
        return str(state.get("transaction_status") or "") in _ACTIVE_TRANSACTION_STATUSES

    @staticmethod
    def _transaction_is_terminal(state: dict[str, Any]) -> bool:
        return str(state.get("transaction_status") or "") in _TERMINAL_TRANSACTION_STATUSES

    def _active_transaction(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """Return only the operationally active transaction.

        Closed transactions are history and must never provide tool/arguments for
        a later turn.  For backward compatibility, an old checkpoint that has the
        legacy selected/pending fields but an ACTIVE status is lazily hydrated into
        ``active_transaction``.
        """
        if not self._transaction_is_active(state):
            return None
        current = state.get("active_transaction")
        if isinstance(current, dict) and current.get("tool_name"):
            return current
        legacy = state.get("pending_tool_call") or state.get("selected_tool_call") or {}
        if not isinstance(legacy, dict) or not legacy.get("tool_name"):
            return None
        current = {
            "transaction_id": str(uuid.uuid4()),
            "tool_name": legacy.get("tool_name"),
            "arguments": dict(legacy.get("arguments") or {}),
            "status": state.get("transaction_status"),
            "started_from_intent": state.get("intent"),
        }
        state["active_transaction"] = current
        return current

    def _set_active_transaction(
        self,
        state: dict[str, Any],
        *,
        tool_name: str,
        arguments: dict[str, Any],
        status: str,
        transaction_id: str | None = None,
    ) -> dict[str, Any]:
        current = state.get("active_transaction") if isinstance(state.get("active_transaction"), dict) else {}
        txid = transaction_id or current.get("transaction_id") or str(uuid.uuid4())
        if str(current.get("tool_name") or "") != str(tool_name):
            state["transaction_pre_validation"] = None
        cfg = self._tool_config(tool_name)
        policy = self._resolve_tool_execution_policy(tool_name, arguments or {})
        tx = {
            "transaction_id": txid,
            "tool_name": tool_name,
            "arguments": dict(arguments or {}),
            "status": status,
            "started_from_intent": current.get("started_from_intent") or state.get("intent"),
            "requires": list(policy.get("requires") or getattr(cfg, "requires", []) or []),
            "parameter_schema": self._transaction_parameter_schema(tool_name, policy),
            "tool_description": self._transaction_tool_description(tool_name),
        }
        state["active_transaction"] = tx
        return tx

    @staticmethod
    def _collect_resource_identifiers(value: Any) -> set[tuple[str, str]]:
        """Collect stable business/resource identifiers from nested evidence.

        Identifier names are deliberately generic (``*_id`` plus common business
        keys) so the framework can correlate transaction evidence across domains
        without embedding telecom/retail-specific behavior.
        """
        identifiers: set[tuple[str, str]] = set()
        common = {
            "resource_key", "customer_key", "contract_key", "account_key",
            "session_key", "subject", "msisdn", "order_id", "invoice_id",
            "asset_id", "product_id", "service_id", "protocol", "protocolo",
        }

        def walk(item: Any) -> None:
            if isinstance(item, dict):
                for key, raw in item.items():
                    key_s = str(key).strip().lower()
                    if raw not in (None, "", [], {}) and (key_s.endswith("_id") or key_s in common):
                        if isinstance(raw, (str, int, float, bool)):
                            identifiers.add((key_s, str(raw).strip().lower()))
                    walk(raw)
            elif isinstance(item, (list, tuple, set)):
                for child in item:
                    walk(child)

        walk(value)
        return identifiers

    def _record_transaction_evidence(
        self,
        state: dict[str, Any],
        *,
        transaction: dict[str, Any] | None,
        status: str,
        result: dict[str, Any] | None,
    ) -> None:
        """Persist compact structured evidence from an executed transaction.

        This is operational evidence, not semantic/LTM memory. It survives later
        turns through the LangGraph state/checkpoint and can be used both by the
        answering LLM and groundedness judges.
        """
        if not isinstance(transaction, dict) or not transaction.get("tool_name"):
            return
        # Only execution outcomes are evidence. A rejected/not-yet-executed action
        # must not become a factual claim about the external system.
        if status not in {"COMPLETED", "FAILED"} or not isinstance(result, dict):
            return

        evidence = {
            "transaction_id": transaction.get("transaction_id"),
            "tool_name": transaction.get("tool_name"),
            "arguments": dict(transaction.get("arguments") or {}),
            "status": status,
            "started_from_intent": transaction.get("started_from_intent"),
            "result": result,
        }
        history = [x for x in (state.get("transaction_evidence") or []) if isinstance(x, dict)]
        txid = evidence.get("transaction_id")
        if txid:
            history = [x for x in history if x.get("transaction_id") != txid]
        history.append(evidence)
        # Bound checkpoint growth while retaining enough recent operational history.
        state["transaction_evidence"] = history[-10:]
        state["last_transaction_evidence"] = evidence

    def transaction_evidence_for_turn(
        self,
        state: dict[str, Any],
        mcp_results: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Return transaction evidence relevant to the current resource/turn."""
        history = [x for x in (state.get("transaction_evidence") or []) if isinstance(x, dict)]
        if not history:
            return []

        current_identifiers = self._collect_resource_identifiers(mcp_results or [])
        if not current_identifiers:
            current_identifiers |= self._collect_resource_identifiers(state.get("business_context") or {})

        if current_identifiers:
            relevant = []
            for evidence in history:
                evidence_ids = self._collect_resource_identifiers(evidence)
                # Match by value as well as key: integrations sometimes rename
                # resource identifiers between transaction/read models.
                current_values = {value for _, value in current_identifiers}
                evidence_values = {value for _, value in evidence_ids}
                if current_identifiers & evidence_ids or current_values & evidence_values:
                    relevant.append(evidence)
            return relevant[-5:]

        # With no resource identifier, expose only the latest evidence to avoid
        # leaking unrelated historical operations into a new topic.
        return history[-1:]

    def _finish_active_transaction(
        self,
        state: dict[str, Any],
        status: str,
        *,
        result: dict[str, Any] | None = None,
    ) -> None:
        """Close the active transaction and retain its result as operational evidence."""
        active = self._active_transaction(state)
        if isinstance(active, dict):
            state["last_transaction"] = {
                **active,
                "status": status,
                **({"result": result} if isinstance(result, dict) else {}),
            }
            self._record_transaction_evidence(
                state, transaction=active, status=status, result=result
            )
        state["active_transaction"] = None
        state["selected_tool_call"] = {}
        state["pending_tool_call"] = {}
        state["missing_parameters"] = []
        state["confirmation_required"] = False
        state["confirmation_received"] = status == "COMPLETED"
        state["next_state"] = None
        state["transaction_status"] = status

    def _normalize_transaction_lifecycle(self, state: dict[str, Any]) -> None:
        """Ensure closed transactions cannot leak into a later user turn."""
        if self._transaction_is_terminal(state):
            # Preserve a compact audit snapshot, but remove every operational latch.
            active = state.get("active_transaction")
            if not isinstance(active, dict):
                legacy = state.get("pending_tool_call") or state.get("selected_tool_call")
                if isinstance(legacy, dict) and legacy.get("tool_name"):
                    active = {
                        "transaction_id": str(uuid.uuid4()),
                        "tool_name": legacy.get("tool_name"),
                        "arguments": dict(legacy.get("arguments") or {}),
                        "status": state.get("transaction_status"),
                        "started_from_intent": state.get("intent"),
                    }
            if isinstance(active, dict):
                state["last_transaction"] = {**active, "status": state.get("transaction_status")}
            state["active_transaction"] = None
            state["selected_tool_call"] = {}
            state["pending_tool_call"] = {}
            state["missing_parameters"] = []
            state["confirmation_required"] = False
            state["confirmation_received"] = False
            state["next_state"] = None
            return
        if self._transaction_is_active(state):
            self._active_transaction(state)

    def transaction_state_patch(self, state: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "available_mcp_tools", "selected_tool_call", "pending_tool_call",
            "transaction_status", "confirmation_required", "confirmation_received",
            "tool_policy_result", "missing_parameters", "next_state", "pending_domain_workflow", "pending_tool_clarification",
            "business_workflows_executed", "active_transaction", "last_transaction",
            "transaction_evidence", "last_transaction_evidence", "relevant_transaction_evidence",
            "transaction_pre_validation",
        )
        return {key: state.get(key) for key in keys if key in state}


    def transaction_clarification_message(self, state: dict[str, Any]) -> str | None:
        """Retorna pergunta determinística para parâmetros ou resultado ambíguo."""
        if state.get("transaction_status") == "TOOL_RESULT_CLARIFICATION":
            pending = state.get("pending_tool_clarification") or {}
            question = str(pending.get("question") or "Qual opção você quis dizer?").strip()
            options = pending.get("options") if isinstance(pending.get("options"), list) else []
            rendered = [f"{idx}. {str(opt.get('label') or opt.get('value') or '').strip()}" for idx, opt in enumerate(options, start=1)]
            rendered = [x for x in rendered if not x.endswith('. ')]
            return question + (("\n" + "\n".join(rendered)) if rendered else "")
        if state.get("transaction_status") != "COLLECTING_PARAMETERS":
            return None
        missing = list(state.get("missing_parameters") or [])
        if not missing:
            return None
        labels = {
            "order_id": "o número do pedido",
            "reason": "o motivo da solicitação",
            "customer_id": "a identificação do cliente",
        }
        friendly = [labels.get(name, str(name).replace("_", " ")) for name in missing]
        if len(friendly) == 1:
            detail = friendly[0]
        else:
            detail = ", ".join(friendly[:-1]) + " e " + friendly[-1]
        return f"Para prosseguir, informe {detail}."

    @staticmethod
    def _missing_required_arguments(policy: dict[str, Any], arguments: dict[str, Any]) -> list[str]:
        return [
            str(name) for name in (policy.get("requires") or [])
            if arguments.get(str(name)) in (None, "", [], {})
        ]

    def _set_collecting_parameters(
        self,
        state: dict[str, Any],
        *,
        tool_name: str,
        arguments: dict[str, Any],
        policy: dict[str, Any],
        missing: list[str],
    ) -> None:
        collecting_state = self._collecting_state_name(state)
        state.update({
            "selected_tool_call": {"tool_name": tool_name, "arguments": arguments},
            "pending_tool_call": {},
            "transaction_status": "COLLECTING_PARAMETERS",
            "confirmation_required": False,
            "confirmation_received": False,
            "missing_parameters": missing,
            "next_state": collecting_state,
            "tool_policy_result": {**policy, "tool_name": tool_name, "action": "collecting_parameters"},
        })
        self._set_active_transaction(
            state, tool_name=tool_name, arguments=arguments, status="COLLECTING_PARAMETERS"
        )

    def transaction_confirmation_message(self, state: dict[str, Any]) -> str | None:
        if state.get("transaction_status") != "AWAITING_CONFIRMATION":
            return None
        pending = state.get("pending_tool_call") or {}
        tool_name = pending.get("tool_name") or "a operação solicitada"
        args = pending.get("arguments") or {}
        order_id = args.get("order_id")
        subject = str(args.get("subject") or "").strip()
        target = f" para o pedido {order_id}" if order_id else ""
        labels = {
            "solicitar_devolucao": "a solicitação de devolução",
            "solicitar_troca": "a solicitação de troca",
        }

        # Confirmações são texto voltado ao cliente. Quando uma ação de
        # cancelamento possui ``subject``, use o nome comercial solicitado
        # em vez de expor o identificador técnico da tool (por exemplo,
        # ``cancelar_vas_avulso`` -> "cancelar vas avulso"). Isso também
        # evita que guardrails de fraseologia bloqueiem uma confirmação
        # transacional legítima por conter nomenclatura interna.
        if tool_name.startswith("cancelar_") and subject:
            return (
                f"Você confirma o cancelamento do serviço {subject}? "
                "Responda 'sim' para executar ou 'não' para cancelar."
            )

        action = labels.get(tool_name, tool_name.replace("_", " "))
        return f"Você confirma {action}{target}? Responda 'sim' para executar ou 'não' para cancelar."

    def _select_read_only_tools(self, available_tools: list[str], text: str) -> list[str]:
        """Seleciona somente as consultas necessárias entre as tools permitidas.

        `selection_keywords` vem de tools.yaml. Se nenhuma tool casar, usa a
        primeira read-only para preservar compatibilidade sem executar todas.
        """
        if len(available_tools) <= 1:
            return list(available_tools)
        normalized = str(text or "").lower()
        matches: list[str] = []
        router = getattr(self, "tool_router", None)
        registry = getattr(router, "registry", None)
        for name in available_tools:
            cfg = registry.get_tool(name) if registry else None
            keywords = list(getattr(cfg, "selection_keywords", None) or [])
            if keywords and any(str(k).lower() in normalized for k in keywords):
                matches.append(name)
        return matches or available_tools[:1]

    @staticmethod
    def _response_path_get(data: Any, path: str | None) -> Any:
        """Resolve caminho simples ``a.b.c`` em dicts sem conhecer o domínio."""
        if not path:
            return data
        current = data
        for part in str(path).split("."):
            if isinstance(current, Mapping):
                current = current.get(part)
            else:
                return None
        return current

    @staticmethod
    def _response_format_value(value: Any, formatter: str | None) -> Any:
        """Formatadores genéricos permitidos pela política declarativa de resposta."""
        if formatter in (None, "", "raw"):
            return value
        if formatter == "decimal_2_comma":
            try:
                return f"{float(value):.2f}".replace(".", ",")
            except (TypeError, ValueError):
                return value
        if formatter == "decimal_2":
            try:
                return f"{float(value):.2f}"
            except (TypeError, ValueError):
                return value
        if formatter == "str":
            return "" if value is None else str(value)
        return value

    @classmethod
    def _response_template(cls, template: str, data: Mapping[str, Any], formats: Mapping[str, Any] | None = None) -> str | None:
        """Renderiza template somente se todos os placeholders existirem.

        Isso evita respostas como ``None`` quando o contrato da tool não corresponde
        à configuração. Nesse caso o runtime cai no fallback legado/LLM.
        """
        formats = formats or {}
        names = set(re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", str(template)))
        values: dict[str, Any] = {}
        for name in names:
            if name not in data or data.get(name) is None:
                return None
            values[name] = cls._response_format_value(data.get(name), formats.get(name))
        try:
            return str(template).format(**values)
        except Exception:
            return None

    def _render_declared_tool_response(self, tool_name: str | None, data: dict[str, Any], *, agent_label: str, state: dict[str, Any] | None = None) -> str | None:
        """Renderiza resposta MCP por configuração, sem regras de negócio no core.

        A configuração vive em ``tools.yaml`` e suporta primitives genéricas:
        ``template``, ``list`` e ``lines``. Se não houver política, retorna ``None``
        para preservar integralmente o comportamento legado.
        """
        router = getattr(self, "tool_router", None)
        registry = getattr(router, "registry", None)
        cfg = registry.get_tool(str(tool_name)) if registry and tool_name else None
        policy = dict(getattr(cfg, "response", None) or {}) if cfg else {}
        if not policy:
            return None

        mode = str(policy.get("mode") or "").strip().lower()

        # Extensão preferencial: o core conhece apenas um nome simbólico.
        # O código do renderer é registrado pela aplicação/domínio.
        if mode == "renderer":
            renderer_name = str(policy.get("renderer") or "").strip()
            if not renderer_name:
                return None
            try:
                from agent_framework.presentation import render_tool_response

                return render_tool_response(
                    renderer_name,
                    tool_name=str(tool_name or ""),
                    result=data,
                    state=state or {},
                    agent_label=agent_label,
                )
            except Exception:
                # Compatibilidade/fail-open: renderer ausente ou com erro não quebra
                # agentes legados; o fluxo continua para o fallback existente.
                return None

        # Modos declarativos da versão anterior são preservados apenas por
        # compatibilidade. Novos projetos devem usar mode=renderer.
        base: dict[str, Any] = {**data, "agent_label": agent_label, "result": data}

        if mode == "template":
            template = policy.get("template")
            if not template:
                return None
            # ``result`` pode ser usado para debug/compatibilidade; demais campos
            # precisam existir para impedir None em texto de cliente.
            if "{result}" in str(template):
                try:
                    return str(template).replace("{result}", str(data)).replace("{agent_label}", agent_label)
                except Exception:
                    return None
            return self._response_template(str(template), base, policy.get("formats"))

        if mode == "list":
            items = self._response_path_get(data, policy.get("source"))
            if not isinstance(items, list) or not items:
                return str(policy.get("empty_message") or "").strip() or None
            rendered_items: list[str] = []
            item_template = str(policy.get("item_template") or "{item}")
            item_formats = policy.get("item_formats") or {}
            for raw in items:
                if isinstance(raw, Mapping):
                    item_data = dict(raw)
                else:
                    item_data = {"item": raw}
                item_data["agent_label"] = agent_label
                line = self._response_template(item_template, item_data, item_formats)
                if line:
                    rendered_items.append(line)
            if not rendered_items:
                return None
            count = len(rendered_items)
            heading_template = policy.get("heading_singular") if count == 1 else policy.get("heading_plural")
            heading = None
            if heading_template:
                heading = self._response_template(
                    str(heading_template),
                    {"agent_label": agent_label, "count": count},
                )
            sep = str(policy.get("separator") or "\n")
            body = sep.join(rendered_items)
            return f"{heading}\n{body}" if heading else body

        if mode == "lines":
            lines: list[str] = []
            for spec in policy.get("lines") or []:
                if not isinstance(spec, Mapping):
                    continue
                kind = str(spec.get("kind") or "template")
                if kind == "template":
                    when = spec.get("when_present")
                    if when and self._response_path_get(data, str(when)) is None:
                        continue
                    line = self._response_template(str(spec.get("template") or ""), base, spec.get("formats"))
                    if line:
                        lines.append(line)
                elif kind == "list":
                    values = self._response_path_get(data, spec.get("source"))
                    if not isinstance(values, list) or not values:
                        continue
                    fields = list(spec.get("item_fields") or ["item"])
                    rendered: list[str] = []
                    for value in values:
                        if isinstance(value, Mapping):
                            chosen = next((value.get(f) for f in fields if value.get(f) not in _EMPTY_VALUES), None)
                        else:
                            chosen = value
                        if chosen not in _EMPTY_VALUES:
                            rendered.append(str(chosen))
                    if rendered:
                        lines.append(
                            str(spec.get("prefix") or "")
                            + str(spec.get("separator") or "; ").join(rendered)
                            + str(spec.get("suffix") or "")
                        )
            if not lines:
                return None
            return str(policy.get("joiner") or " ").join(lines)

        if mode == "field":
            value = self._response_path_get(data, policy.get("field"))
            return str(value).strip() if value not in _EMPTY_VALUES else None

        if mode in {"llm", "none"}:
            return None
        return None

    def build_direct_mcp_answer(self, state: dict[str, Any], mcp_results: list[dict[str, Any]], *, agent_label: str) -> str | None:
        """Retorna resposta MCP direta somente quando a aplicação declarar isso explicitamente.

        Um resultado de tool não implica, por si só, que a pergunta do usuário foi
        respondida. O core do framework não conhece nomes de tools nem formatos de
        domínio. Para encerrar o fluxo antes de RAG/LLM, a configuração da tool deve
        declarar ``response.direct: true`` e fornecer uma política de apresentação
        válida. Sem essa declaração, o fluxo continua para retrieval/composição.
        """
        requires_rag, _ = self._mcp_rag_directive(mcp_results)
        requires_llm_composition, _ = self._mcp_llm_composition_directive(mcp_results)
        if requires_rag or requires_llm_composition:
            return None

        ok = [r for r in mcp_results if r.get("ok") and isinstance(r.get("result"), dict)]
        for item in ok:
            workflow = self._workflow_payload_from_tool_result(item)
            if workflow and workflow.get("status") == "PAUSED":
                pause = workflow.get("pause") if isinstance(workflow.get("pause"), dict) else {}
                prompt = pause.get("prompt")
                if prompt:
                    return str(prompt)
            if workflow and workflow.get("status") == "COMPLETED":
                # A completed workflow is not automatically a direct answer. Only
                # the terminal node may provide an explicit message. Searching
                # backwards for any prior ``mensagem`` can replay a prompt emitted
                # before a pause (e.g. the question the user has just answered) and
                # suppress the normal LLM/orchestrator composition of terminal data.
                nodes = workflow.get("output") if isinstance(workflow.get("output"), dict) else {}
                workflow_state = workflow.get("state") if isinstance(workflow.get("state"), dict) else {}
                terminal_node = str(workflow_state.get("current_node") or "").strip()
                terminal_output = nodes.get(terminal_node) if terminal_node else None
                if isinstance(terminal_output, dict) and str(terminal_output.get("mensagem") or "").strip():
                    return str(terminal_output["mensagem"]).strip()

        text = state.get("sanitized_input") or state.get("user_text") or ""
        if (
            len(ok) != 1
            or state.get("transaction_status")
            or self._transactional_action_match(str(text)) is not None
        ):
            return None

        tool = ok[0].get("tool_name")
        data = ok[0]["result"]
        router = getattr(self, "tool_router", None)
        registry = getattr(router, "registry", None)
        cfg = registry.get_tool(str(tool)) if registry and tool else None
        policy = dict(getattr(cfg, "response", None) or {}) if cfg else {}

        # Importante: renderer/template descreve COMO apresentar uma resposta;
        # somente ``direct: true`` declara que ela é semanticamente suficiente
        # para encerrar o turno antes de RAG/LLM.
        if not bool(policy.get("direct", False)):
            return None

        return self._render_declared_tool_response(tool, data, agent_label=agent_label, state=state)

    def _clear_active_interaction_context_on_route_shift(self, state: dict[str, Any]) -> bool:
        """Invalidate active conversational latches when routing leaves their owner.

        This is deliberately generic.  It compares the current route decision with
        the owner recorded by a paused workflow; it does not inspect domain, tool,
        workflow or intent names.  Durable checkpoints/history remain intact.
        """
        pending_workflow = state.get("pending_domain_workflow")
        if not isinstance(pending_workflow, dict) or not pending_workflow.get("execution_id"):
            return False

        route_decision = state.get("route_decision") if isinstance(state.get("route_decision"), dict) else {}
        route_metadata = route_decision.get("metadata") if isinstance(route_decision.get("metadata"), dict) else {}
        if route_metadata.get("workflow_resume"):
            return False

        current_intent = str(route_decision.get("intent") or state.get("intent") or "").strip()
        current_agent = str(route_decision.get("agent") or route_decision.get("route") or state.get("route") or "").strip()
        owner_intent = str(pending_workflow.get("owner_intent") or "").strip()
        owner_agent = str(pending_workflow.get("owner_agent") or "").strip()

        intent_changed = bool(owner_intent and current_intent and owner_intent != current_intent)
        agent_changed = bool(owner_agent and current_agent and owner_agent != current_agent)
        if not (intent_changed or agent_changed):
            return False

        state["last_interrupted_domain_workflow"] = {
            **pending_workflow,
            "status": "CANCELLED",
            "reason": "intent_shift",
        }
        state["pending_domain_workflow"] = None

        # The active interaction owns all operational latches, not the durable
        # audit trail. Clear only live state so a new semantic route starts clean.
        active_tx = self._active_transaction(state)
        if isinstance(active_tx, dict) and active_tx.get("tool_name"):
            self._finish_active_transaction(state, "CANCELLED")
        else:
            state["active_transaction"] = None
            state["selected_tool_call"] = {}
            state["pending_tool_call"] = {}
            state["missing_parameters"] = []
            state["confirmation_required"] = False
            state["confirmation_received"] = False
            state["next_state"] = None

        if state.get("transaction_status") in {"WORKFLOW_PAUSED", "COLLECTING_PARAMETERS", "AWAITING_CONFIRMATION", "CANCELLED"}:
            state["transaction_status"] = None
        state["transaction_pre_validation"] = None
        state["pending_tool_clarification"] = None
        state["tool_policy_result"] = {
            "action": "cleared_by_intent_shift",
            "workflow_execution_id": pending_workflow.get("execution_id"),
        }
        state["mcp_results"] = []
        return True

    async def execute_tools_for_intent(
        self,
        state: dict[str, Any],
        *,
        tools: list[str] | None = None,
        aliases: dict[str, Iterable[str]] | None = None,
        emit_events: bool = True,
    ) -> list[dict[str, Any]]:
        """Executa consultas e controla ações transacionais.

        ``mcp_tools`` é uma allowlist. Tools read-only podem enriquecer o contexto;
        uma tool transacional só é selecionada quando a mensagem expressa a ação.
        Quando a política exige confirmação, a chamada é persistida no state e só
        executada em um turno posterior confirmado.
        """
        results: list[dict[str, Any]] = []
        available_tools = list(tools if tools is not None else (state.get("mcp_tools") or []))
        state["available_mcp_tools"] = available_tools
        text = state.get("sanitized_input") or state.get("user_text") or ""
        self._normalize_transaction_lifecycle(state)

        # Uma transação em coleta/confirmação não pode aprisionar a sessão. O
        # EnterpriseRouter é a única fonte para interrupção por mudança de intent.
        # Não existe interpretação lexical de desistência no runtime: mudou a
        # intent, a transação anterior é encerrada e seus latches são limpos.
        active_before_interruption = self._active_transaction(state)
        route_meta = (state.get("route_decision") or {}).get("metadata") or {}
        interruption = str(route_meta.get("transaction_interruption") or "").strip().lower()
        if active_before_interruption and interruption == "intent_shift":
            interrupted_tool = active_before_interruption.get("tool_name")
            self._finish_active_transaction(state, "CANCELLED")
            state["transaction_pre_validation"] = None
            state["tool_policy_result"] = {
                "action": "cancelled_by_intent_shift",
                "tool_name": interrupted_tool,
            }

        self._clear_active_interaction_context_on_route_shift(state)

        # Clarificação de resultado de tool tem precedência: reutiliza a mesma tool
        # e argumentos, alterando apenas o parâmetro escolhido pelo usuário.
        if state.get("pending_tool_clarification"):
            resumed = await self._resume_pending_tool_clarification(state, str(text))
            return [resumed] if resumed else []

        # Workflows conversacionais pausados têm precedência sobre novo roteamento/tool selection.
        # O domínio informa apenas workflow/execution_id; a retomada é uma capability genérica.
        if state.get("pending_domain_workflow"):
            resumed = await self._resume_pending_domain_workflow(state, str(text))
            return [resumed] if resumed else []

        # Antes de confirmar, complete os parâmetros obrigatórios da ação.
        if state.get("transaction_status") == "COLLECTING_PARAMETERS":
            selected = dict(self._active_transaction(state) or state.get("selected_tool_call") or {})
            tool_name = selected.get("tool_name")
            if tool_name:
                previous_args = dict(selected.get("arguments") or {})
                policy = self._resolve_tool_execution_policy(tool_name, previous_args)
                missing_before = self._missing_required_arguments(policy, previous_args)

                # Parâmetros TRANSACIONAIS são interpretados exclusivamente pelo
                # extrator LLM genérico. Não existem regexes/nome de entidade
                # hardcoded no framework. O extrator recebe apenas os parâmetros
                # ainda pendentes da policy e pode consumir um ou vários no turno.
                extracted = await self._extract_transaction_parameters(
                    state,
                    tool_name=tool_name,
                    missing_parameters=missing_before,
                    known_arguments=previous_args,
                )
                arguments = {**previous_args, **extracted}

                # Argumentos estruturados já presentes no contexto são aceitos de
                # forma genérica (não são parsing textual). Para required fields,
                # só completam lacunas que a fala atual/LLM não preencheu; valores
                # previamente coletados nunca são sobrescritos.
                contextual = self.build_tool_arguments(
                    state, tool_name=tool_name, intent=state.get("intent"), aliases=aliases
                )
                required_set = set(str(name) for name in (policy.get("requires") or []))
                for key, value in contextual.items():
                    if value in _EMPTY_VALUES:
                        continue
                    if key in required_set:
                        if arguments.get(key) in _EMPTY_VALUES:
                            arguments[key] = value
                    else:
                        arguments[key] = value
                arguments = await self._extract_mcp_parameters(
                    tool_name, arguments, state, exclude_fields=policy.get("requires") or []
                )
                policy = self._resolve_tool_execution_policy(tool_name, arguments)
                missing = self._missing_required_arguments(policy, arguments)
                if missing:
                    self._set_collecting_parameters(
                        state, tool_name=tool_name, arguments=arguments, policy=policy, missing=missing
                    )
                    return [{
                        "ok": True,
                        "executed": False,
                        "tool_name": tool_name,
                        "collecting_parameters": True,
                        "transaction_status": "COLLECTING_PARAMETERS",
                        "missing_parameters": missing,
                        "metadata": policy,
                    }]

                selected = {"tool_name": tool_name, "arguments": arguments}
                state["selected_tool_call"] = selected
                self._set_active_transaction(
                    state, tool_name=tool_name, arguments=arguments, status="COLLECTING_PARAMETERS"
                )
                state["missing_parameters"] = []
                pre_validation_result = await self._run_transaction_pre_validation(
                    state, tool_name=tool_name, arguments=arguments, policy=policy, emit_events=emit_events
                )
                if pre_validation_result is not None:
                    return [pre_validation_result]

                if policy.get("require_confirmation"):
                    waiting_state = self._waiting_state_name(state)
                    state.update({
                        "pending_tool_call": selected,
                        "transaction_status": "AWAITING_CONFIRMATION",
                        "confirmation_required": True,
                        "confirmation_received": False,
                        "next_state": waiting_state,
                        "tool_policy_result": {**policy, "tool_name": tool_name},
                    })
                    self._set_active_transaction(
                        state, tool_name=tool_name, arguments=arguments, status="AWAITING_CONFIRMATION"
                    )
                    return [{
                        "ok": True,
                        "executed": False,
                        "tool_name": tool_name,
                        "awaiting_confirmation": True,
                        "transaction_status": "AWAITING_CONFIRMATION",
                        "metadata": policy,
                    }]

                arguments["confirmed"] = True
                result = await self._call_mcp_tool(tool_name, arguments, state)
                self._capture_pending_domain_workflow(state, result)
                self._capture_pending_tool_clarification(state, result, tool_name=tool_name, arguments=arguments)
                final_status = ("WORKFLOW_PAUSED" if state.get("pending_domain_workflow") else ("TOOL_RESULT_CLARIFICATION" if state.get("pending_tool_clarification") else ("COMPLETED" if result.get("ok") else "FAILED")))
                if final_status in _TERMINAL_TRANSACTION_STATUSES:
                    self._finish_active_transaction(state, final_status, result=result)
                else:
                    state.update({
                        "transaction_status": final_status,
                        "confirmation_required": False,
                        "confirmation_received": True,
                        "pending_tool_call": {},
                        "missing_parameters": [],
                    })
                    self._set_active_transaction(
                        state, tool_name=tool_name, arguments=arguments, status=final_status
                    )
                return [result]

        active_tx = self._active_transaction(state)
        pending = (active_tx if isinstance(active_tx, dict) and active_tx.get("status") == "AWAITING_CONFIRMATION" else state.get("pending_tool_call")) or {}
        if pending:
            decision = self._confirmation_decision(text)
            if decision == "reject":
                state["tool_policy_result"] = {"action": "cancelled", "tool_name": pending.get("tool_name")}
                self._finish_active_transaction(state, "CANCELLED")
                return [{"ok": True, "tool_name": pending.get("tool_name"), "transaction_status": "CANCELLED", "cancelled": True}]
            if decision == "confirm":
                tool_name = pending.get("tool_name")
                arguments = dict(pending.get("arguments") or {})
                arguments["confirmed"] = True
                state["confirmation_received"] = True
                result = await self._call_mcp_tool(tool_name, arguments, state)
                self._capture_pending_domain_workflow(state, result)
                self._capture_pending_tool_clarification(state, result, tool_name=tool_name, arguments=arguments)
                final_status = ("WORKFLOW_PAUSED" if state.get("pending_domain_workflow") else ("TOOL_RESULT_CLARIFICATION" if state.get("pending_tool_clarification") else ("COMPLETED" if result.get("ok") else "FAILED")))
                state["tool_policy_result"] = {"action": "executed_after_confirmation", "tool_name": tool_name}
                if final_status in _TERMINAL_TRANSACTION_STATUSES:
                    self._finish_active_transaction(state, final_status, result=result)
                else:
                    state.update({
                        "transaction_status": final_status,
                        "confirmation_required": False,
                        "pending_tool_call": {},
                    })
                    self._set_active_transaction(
                        state, tool_name=tool_name, arguments=arguments, status=final_status
                    )
                results.append(result)
                return results
            state["transaction_status"] = "AWAITING_CONFIRMATION"
            state["confirmation_required"] = True
            self._set_active_transaction(
                state, tool_name=str(pending.get("tool_name") or ""), arguments=dict(pending.get("arguments") or {}), status="AWAITING_CONFIRMATION"
            )
            return [{"ok": False, "tool_name": pending.get("tool_name"), "awaiting_confirmation": True, "transaction_status": "AWAITING_CONFIRMATION"}]

        read_only_tools = [
            tool for tool in available_tools
            if self._resolve_tool_execution_policy(tool).get("operation_type") != "transactional"
        ]
        read_only_tools = self._select_read_only_tools(read_only_tools, text)
        state["selected_read_only_tools"] = read_only_tools
        for tool in read_only_tools:
            args = self.build_tool_arguments(state, tool_name=tool, intent=state.get("intent"), aliases=aliases)
            allowed, reason = self._validate_tool_execution_policy(tool, args)
            if not allowed:
                results.append({"ok": False, "tool_name": tool, "skipped": True, "reason": reason})
                if emit_events:
                    await self._emit_ic("IC.TOOL_SKIPPED_BY_POLICY", state, {"tool_name": tool, "reason": reason}, component="agent_runtime.tool_policy")
                continue
            if emit_events:
                await self._emit_ic("IC.MCP_TOOL_REQUESTED", state, {"tool_name": tool, "operation_type": "read_only"}, component="agent_runtime")
            result = await self._call_mcp_tool(tool, args, state)
            self._capture_pending_domain_workflow(state, result)
            self._capture_pending_tool_clarification(state, result, tool_name=tool, arguments=args)
            results.append(result)
            if emit_events:
                await self._emit_ic(
                    "IC.TOOL_CALLED",
                    state,
                    {
                        "tool_name": tool,
                        "ok": result.get("ok"),
                        "server_name": result.get("server_name"),
                        "error": result.get("error"),
                        "cached": bool(result.get("cached")),
                    },
                    component="agent_runtime",
                )
                if not result.get("ok"):
                    await self._emit_noc("NOC.MCP_TOOL_FAILED", state, {"tool_name": tool, "error": result.get("error")}, component="agent_runtime")

        selected_action = self._select_transactional_tool(available_tools, text)
        if not selected_action:
            return results

        action_args = self.build_tool_arguments(
            state,
            tool_name=selected_action,
            intent=state.get("intent"),
            aliases=aliases,
        )
        # Campos que o contrato MCP declara como vindos da mensagem corrente não
        # podem herdar valores textuais de uma transação anterior. Isto é apenas
        # uma regra de freshness do envelope MCP; a extração de policy.requires
        # continua exclusivamente no TransactionParameterExtractor LLM abaixo.
        action_args = self._drop_stale_message_extracted_arguments(
            selected_action, action_args, explicit_fields=()
        )
        policy = self._resolve_tool_execution_policy(selected_action, action_args)
        required = [str(name) for name in (policy.get("requires") or [])]

        # Valores já estruturados no contexto podem satisfazer requirements sem
        # parsing textual. Para qualquer required field ainda ausente, a fala do
        # usuário é interpretada exclusivamente pelo extrator LLM transacional.
        missing_initial = self._missing_required_arguments(policy, action_args)
        # No primeiro turno, a fala atual pode fornecer/corrigir qualquer required
        # field, inclusive um valor que exista no contexto estruturado mas pertença
        # a uma transação anterior. O extrator continua restrito ao contrato
        # ``requires`` e só sobrescreve quando a LLM realmente extrai um valor.
        extracted_initial = await self._extract_transaction_parameters(
            state,
            tool_name=selected_action,
            missing_parameters=required,
            known_arguments={k: v for k, v in action_args.items() if k not in set(required)},
        )
        action_args.update(extracted_initial)

        # O mapper MCP continua responsável somente por parâmetros auxiliares que
        # não pertencem ao contrato transacional.
        action_args = await self._extract_mcp_parameters(
            selected_action,
            action_args,
            state,
            overwrite_from_message=True,
            exclude_fields=required,
        )
        policy = self._resolve_tool_execution_policy(selected_action, action_args)
        selected = {"tool_name": selected_action, "arguments": action_args}
        state["selected_tool_call"] = selected
        self._set_active_transaction(
            state, tool_name=selected_action, arguments=action_args, status="COLLECTING_PARAMETERS"
        )
        state["tool_policy_result"] = {**policy, "tool_name": selected_action}

        missing = self._missing_required_arguments(policy, action_args)
        if missing:
            self._set_collecting_parameters(
                state,
                tool_name=selected_action,
                arguments=action_args,
                policy=policy,
                missing=missing,
            )
            if emit_events:
                await self._emit_ic(
                    "IC.TRANSACTION_PARAMETERS_REQUIRED",
                    state,
                    {"tool_name": selected_action, "missing_parameters": missing, **policy},
                    component="agent_runtime.tool_policy",
                )
            results.append({
                "ok": True,
                "executed": False,
                "tool_name": selected_action,
                "collecting_parameters": True,
                "transaction_status": "COLLECTING_PARAMETERS",
                "missing_parameters": missing,
                "metadata": policy,
            })
            return results

        pre_validation_result = await self._run_transaction_pre_validation(
            state, tool_name=selected_action, arguments=action_args, policy=policy, emit_events=emit_events
        )
        if pre_validation_result is not None:
            results.append(pre_validation_result)
            return results

        if policy.get("require_confirmation"):
            state.update({
                "pending_tool_call": selected,
                "transaction_status": "AWAITING_CONFIRMATION",
                "confirmation_required": True,
                "confirmation_received": False,
            })
            self._set_active_transaction(
                state, tool_name=selected_action, arguments=action_args, status="AWAITING_CONFIRMATION"
            )
            state["next_state"] = self._waiting_state_name(state)
            if emit_events:
                await self._emit_ic("IC.TRANSACTION_CONFIRMATION_REQUIRED", state, {"tool_name": selected_action, **policy}, component="agent_runtime.tool_policy")
            results.append({"ok": False, "tool_name": selected_action, "awaiting_confirmation": True, "transaction_status": "AWAITING_CONFIRMATION", "metadata": policy})
            return results

        action_args["confirmed"] = True
        result = await self._call_mcp_tool(selected_action, action_args, state)
        self._capture_pending_domain_workflow(state, result)
        final_status = ("WORKFLOW_PAUSED" if state.get("pending_domain_workflow") else ("TOOL_RESULT_CLARIFICATION" if state.get("pending_tool_clarification") else ("COMPLETED" if result.get("ok") else "FAILED")))
        if final_status in _TERMINAL_TRANSACTION_STATUSES:
            self._finish_active_transaction(state, final_status, result=result)
        else:
            state.update({
                "transaction_status": final_status,
                "confirmation_required": False,
                "confirmation_received": True,
                "pending_tool_call": {},
            })
            self._set_active_transaction(
                state, tool_name=selected_action, arguments=action_args, status=final_status
            )
        results.append(result)
        return results

    async def _collect_mcp_context(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        results = await self.execute_tools_for_intent(state)
        # Materialize the relevant prior operational evidence in graph state so
        # downstream nodes (output supervision/judges/telemetry) consume the same
        # evidence set used by the answering agent.
        state["relevant_transaction_evidence"] = self.transaction_evidence_for_turn(state, results)
        return results

    # ------------------------------------------------------------------
    # Conversation memory / context compression
    # ------------------------------------------------------------------
    async def prepare_memory_context(
        self,
        state: dict[str, Any],
        *,
        session_id: str | None = None,
        force: bool = False,
    ) -> MemoryContext | None:
        """Prepara memória conversacional para o próximo prompt.

        Esta etapa é assíncrona porque pode consultar banco e, quando a
        estratégia for `summary`, chamar o LLM para compactar mensagens antigas.
        O resultado é salvo em `state['memory_context']`; o método sync
        `build_messages()` apenas injeta esse contexto já preparado.
        """
        settings = getattr(self, "settings", None)
        if not settings:
            return None

        runtime = self.get_runtime_context(state)
        resolved_session_id = (
            session_id
            or state.get("conversation_key")
            or state.get("session_id")
            or runtime.session.get("backend_session_id")
            or runtime.session.get("global_session_id")
            or runtime.session.get("session_id")
        )
        if not resolved_session_id:
            return None

        summary_memory = getattr(self, "summary_memory", None)
        if summary_memory is None:
            from agent_framework.memory.message_history import create_memory
            from agent_framework.memory.summary_memory import create_conversation_summary_memory

            message_history = (
                getattr(self, "memory", None)
                or getattr(self, "message_history", None)
                or create_memory(settings)
            )
            summary_memory = create_conversation_summary_memory(
                settings,
                message_history=message_history,
                llm=getattr(self, "llm", None),
                telemetry=getattr(self, "telemetry", None),
            )
            try:
                self.summary_memory = summary_memory
            except Exception:
                pass

        memory_context = await summary_memory.prepare_context(resolved_session_id, force=force)
        state["memory_context"] = memory_context
        state["memory_context_metadata"] = memory_context.metadata

        if bool(getattr(settings, "ENABLE_LONG_TERM_MEMORY", False)):
            manager = getattr(self, "long_term_memory_manager", None)
            if manager is None:
                from agent_framework.memory.long_term_memory import create_long_term_memory_manager
                manager = create_long_term_memory_manager(settings, telemetry=getattr(self, "telemetry", None))
                self.long_term_memory_manager = manager
            items = await manager.load(state)
            state["long_term_memories"] = [item.to_dict() for item in items]
            state["long_term_memory_context"] = manager.render(items)

        if memory_context.compressed:
            await self._emit_ic(
                "IC.MEMORY_COMPRESSION_TRIGGERED",
                state,
                {"session_id": resolved_session_id, **memory_context.metadata},
                component="agent_runtime.memory",
            )
        elif memory_context.has_content():
            await self._emit_ic(
                "IC.MEMORY_CONTEXT_LOADED",
                state,
                {"session_id": resolved_session_id, **memory_context.metadata},
                component="agent_runtime.memory",
            )
        return memory_context

    def _coerce_memory_context(self, value: Any) -> MemoryContext | None:
        if value is None:
            return None
        if isinstance(value, MemoryContext):
            return value
        if isinstance(value, dict):
            return MemoryContext(
                summary=str(value.get("summary") or ""),
                recent_messages=list(value.get("recent_messages") or []),
                compressed=bool(value.get("compressed", False)),
                metadata=dict(value.get("metadata") or {}),
            )
        return None

    def _render_memory_sections(self, state: dict[str, Any]) -> list[str]:
        settings = getattr(self, "settings", None)
        memory_context = self._coerce_memory_context(state.get("memory_context"))
        if not memory_context or not memory_context.has_content():
            return []

        inject_summary = bool(getattr(settings, "MEMORY_INJECT_SUMMARY", True)) if settings else True
        inject_recent = bool(getattr(settings, "MEMORY_INJECT_RECENT_MESSAGES", True)) if settings else True
        sections: list[str] = []
        if inject_summary and memory_context.summary:
            sections.append(f"Resumo da conversa até agora:\n{memory_context.summary}")
        if inject_recent and memory_context.recent_messages:
            # recent_messages pode vir como ChatMessage ou dict em testes.
            normalized = []
            for item in memory_context.recent_messages:
                if hasattr(item, "role") and hasattr(item, "content"):
                    normalized.append(item)
                elif isinstance(item, dict):
                    from agent_framework.models.session import ChatMessage

                    normalized.append(ChatMessage(role=item.get("role", "unknown"), content=item.get("content", ""), metadata=item.get("metadata") or {}))
            rendered = render_recent_messages(normalized)
            if rendered:
                sections.append(f"Últimas mensagens completas da conversa:\n{rendered}")
        return sections

    # ------------------------------------------------------------------
    # Messages / LLM / cache
    # ------------------------------------------------------------------
    def build_messages(
        self,
        state: dict[str, Any],
        *,
        system_prompt: str,
        user_text: str | None = None,
        mcp_results: list[dict[str, Any]] | None = None,
        rag_context: str | None = None,
        rag_metadata: dict[str, Any] | None = None,
        include_business_context: bool = True,
        extra_sections: dict[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        runtime = self.get_runtime_context(state)
        sections = []
        sections.extend(self._render_memory_sections(state))
        if bool(getattr(getattr(self, "settings", None), "LONG_TERM_MEMORY_INJECT_CONTEXT", True)) and state.get("long_term_memory_context"):
            sections.append(str(state["long_term_memory_context"]))
        sections.extend([
            f"Mensagem do usuário:\n{user_text if user_text is not None else runtime.sanitized_input}",
            f"Intent/rota escolhidos pelo framework:\nintent={state.get('intent')} route={state.get('route')}",
        ])
        if include_business_context:
            sections.append(f"BusinessContext canônico:\n{runtime.business_context or '[sem business_context]'}")
        if mcp_results is not None:
            sections.append(f"Resultados MCP normalizados pelo framework:\n{mcp_results}")
        transaction_evidence = self.transaction_evidence_for_turn(state, mcp_results)
        if transaction_evidence:
            sections.append(
                "Evidências operacionais de transações anteriores relevantes ao recurso atual "
                f"(persistidas pelo framework, não inferidas pela memória conversacional):\n{transaction_evidence}"
            )
        if rag_context is not None:
            sections.append(f"Contexto de conhecimento (RAG):\n{rag_context or '[sem contexto RAG]'}")
        if rag_metadata is not None:
            sections.append(f"Metadados RAG:\n{rag_metadata}")
            provider = str(rag_metadata.get("provider") or getattr(getattr(self, "settings", None), "RAG_PROVIDER", "standard"))
            grounded_only = bool(getattr(getattr(self, "settings", None), "RAG_GROUNDED_ONLY", False))
            if provider == "kbdb":
                grounded_only = bool(getattr(getattr(self, "settings", None), "KBDB_GROUNDED_ONLY", True))
            if grounded_only:
                sections.append(
                    "Política de grounding obrigatória:\n"
                    "- Use como fatos somente evidências presentes nos resultados MCP, no contexto RAG e no business context fornecido.\n"
                    "- Não complete lacunas usando conhecimento paramétrico do modelo, memória geral ou suposições.\n"
                    "- Se a informação pedida não estiver sustentada pelas evidências disponíveis, diga explicitamente que não há informação suficiente na base consultada.\n"
                    "- Se o RAG estiver vazio, bloqueado ou com erro, ainda é permitido responder apenas a partes comprovadas por MCP/business context; não invente a parte documental ausente."
                )
        for title, value in (extra_sections or {}).items():
            sections.append(f"{title}:\n{value}")
        return MessageBuilder(state).system(system_prompt).user("\n\n".join(sections)).build()

    async def _cache_get(self, key: str):
        cache = getattr(self, "cache", None)
        if not cache:
            return None
        return await cache.get(key)

    async def _cache_set(self, key: str, value: Any, ttl_seconds: int | None = None):
        cache = getattr(self, "cache", None)
        if not cache:
            return
        await cache.set(key, value, ttl_seconds)

    def _llm_cache_key(self, state: dict[str, Any], agent_name: str, prompt_parts: list[Any]) -> str:
        runtime = self.get_runtime_context(state)
        # Include the effective LLM profile in the cache key so a model/parameter
        # change in llm_profiles.yaml does not reuse an answer generated by another
        # model configuration. If the provider has no resolver, this is a harmless
        # empty marker and preserves the previous behavior.
        profile_marker = ""
        llm = getattr(self, "llm", None)
        resolver = getattr(llm, "profile_resolver", None)
        if resolver is not None:
            try:
                effective_profile = resolver.resolve(agent_name)
                profile_marker = repr({
                    "profile_name": effective_profile.get("profile_name"),
                    "provider": effective_profile.get("provider"),
                    "model": effective_profile.get("model"),
                    "temperature": effective_profile.get("temperature"),
                    "max_tokens": effective_profile.get("max_tokens"),
                    "top_p": effective_profile.get("top_p"),
                })
            except Exception:
                profile_marker = "profile_unavailable"
        raw = "|".join([
            agent_name,
            profile_marker,
            state.get("tenant_id") or "",
            state.get("agent_id") or "",
            state.get("intent") or "",
            str(runtime.business_context.get("customer_key") or ""),
            str(runtime.business_context.get("contract_key") or ""),
            str(runtime.business_context.get("interaction_key") or ""),
            runtime.sanitized_input or "",
            repr(prompt_parts),
        ])
        return "llm:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def _invoke_llm_cached(self, state: dict[str, Any], agent_name: str, messages: list[dict[str, str]]):
        ttl = int(getattr(getattr(self, "settings", None), "CACHE_TTL_SECONDS", 300) or 300)
        key = self._llm_cache_key(state, agent_name, messages)
        cached = await self._cache_get(key)
        telemetry = getattr(self, "telemetry", None)
        if cached is not None:
            if telemetry:
                await telemetry.event("cache.llm.hit", {"agent": agent_name, "key": key}, kind="cache")
            return cached
        if telemetry:
            await telemetry.event("cache.llm.miss", {"agent": agent_name, "key": key}, kind="cache")
        answer = await self.llm.ainvoke(messages, profile_name=agent_name, component_name=agent_name, generation_name=f"llm.{agent_name}")
        await self._cache_set(key, answer, ttl)
        return answer

    def build_llm_fallback_answer(self, state: dict[str, Any], mcp_results: list[dict[str, Any]], *, agent_label: str | None = None) -> str:
        ok_tools = [r.get("tool_name") or r.get("tool") for r in mcp_results if r.get("ok")]
        failed_tools = [r.get("tool_name") or r.get("tool") for r in mcp_results if not r.get("ok")]
        label = agent_label or getattr(self, "name", "Agent")
        return (
            f"[{label}] Fluxo executado pelo framework. "
            f"Intent: {state.get('intent')}. "
            f"Tools com sucesso: {ok_tools or 'nenhuma'}. "
            f"Tools pendentes/erro: {failed_tools or 'nenhuma'}. "
            "A resposta final não foi enriquecida pelo LLM porque houve falha controlada nessa etapa."
        )
