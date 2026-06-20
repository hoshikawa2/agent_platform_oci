from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


from agent_framework.memory.summary_memory import MemoryContext, render_recent_messages


logger = logging.getLogger(__name__)

_EMPTY_VALUES = (None, "", {}, [])


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

    # ------------------------------------------------------------------
    # RAG
    # ------------------------------------------------------------------
    async def _retrieve_rag_context(self, state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        rag_service = getattr(self, "rag_service", None)
        if not rag_service:
            return "", {"enabled": False}
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
        result = await rag_service.retrieve(runtime.sanitized_input, namespace=namespace, graph_node=graph_node, rewrite=rewrite)
        if bool(getattr(settings, "ENABLE_RAG_CONTEXT_COMPRESSION", False)) and hasattr(rag_service, "compress_context"):
            context = await rag_service.compress_context(result, question=runtime.sanitized_input)
        else:
            context = result.as_prompt_context()
        return context, {
            "enabled": True,
            "namespace": namespace,
            "latency_ms": result.latency_ms,
            "document_count": len(result.documents),
            "graph_neighbors": len(result.graph_neighbors),
            "top_document_ids": [d.id for d in result.documents[:5]],
            "top_scores": [d.score for d in result.documents[:5]],
            "rewritten": result.metadata.get("rewritten"),
            "effective_query": result.query,
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

    def _tool_config(self, tool_name: str) -> Any:
        router = getattr(self, "tool_router", None)
        registry = getattr(router, "registry", None)
        if registry and hasattr(registry, "get_tool"):
            return registry.get_tool(tool_name)
        return None

    def _validate_tool_execution_policy(self, tool_name: str, arguments: dict[str, Any]) -> tuple[bool, str | None]:
        """Aplica política genérica de execução declarada em tools.yaml."""
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
        return result

    async def _call_mcp_tool(self, tool_name: str, arguments: dict[str, Any] | None, state: dict[str, Any]) -> dict[str, Any]:
        args = arguments or {}
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

    async def execute_tools_for_intent(
        self,
        state: dict[str, Any],
        *,
        tools: list[str] | None = None,
        aliases: dict[str, Iterable[str]] | None = None,
        emit_events: bool = True,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        selected_tools = list(tools if tools is not None else (state.get("mcp_tools") or []))
        for tool in selected_tools:
            args = self.build_tool_arguments(state, tool_name=tool, intent=state.get("intent"), aliases=aliases)
            allowed, reason = self._validate_tool_execution_policy(tool, args)
            if not allowed:
                result = {"ok": False, "tool_name": tool, "skipped": True, "reason": reason}
                results.append(result)
                if emit_events:
                    await self._emit_ic("IC.TOOL_SKIPPED_BY_POLICY", state, {"tool_name": tool, "reason": reason}, component="agent_runtime.tool_policy")
                continue
            if emit_events:
                await self._emit_ic("IC.MCP_TOOL_REQUESTED", state, {"tool_name": tool}, component="agent_runtime")
            result = await self._call_mcp_tool(tool, args, state)
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
        return results

    async def _collect_mcp_context(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        return await self.execute_tools_for_intent(state)

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
        sections.extend([
            f"Mensagem do usuário:\n{user_text if user_text is not None else runtime.sanitized_input}",
            f"Intent/rota escolhidos pelo framework:\nintent={state.get('intent')} route={state.get('route')}",
        ])
        if include_business_context:
            sections.append(f"BusinessContext canônico:\n{runtime.business_context or '[sem business_context]'}")
        if mcp_results is not None:
            sections.append(f"Resultados MCP normalizados pelo framework:\n{mcp_results}")
        if rag_context is not None:
            sections.append(f"Contexto RAG nativo do framework:\n{rag_context or '[sem contexto RAG]'}")
        if rag_metadata is not None:
            sections.append(f"Metadados RAG:\n{rag_metadata}")
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
