from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from .models import MCPServerConfig, MCPToolResult

logger = logging.getLogger("agent_framework.mcp.client")


class MCPHttpClient:
    """MCP client with two compatible modes.

    - transport=http keeps the framework's legacy simple contract:
      GET  <endpoint>/tools/list
      POST <endpoint>/tools/call {"tool_name": "...", "arguments": {...}}

    - transport=fastmcp|streamable_http|sse uses the official MCP Python client
      and can call FastMCP servers directly.
    """

    def __init__(self, timeout_seconds: int = 30):
        self.timeout_seconds = timeout_seconds

    async def list_tools(self, server: MCPServerConfig) -> list[dict[str, Any]]:
        if server.transport in {"fastmcp", "streamable_http", "sse"}:
            return await self._list_fastmcp_tools(server)
        return await self._list_legacy_http_tools(server)

    async def call_tool(
        self,
        server: MCPServerConfig,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> MCPToolResult:
        if server.transport in {"fastmcp", "streamable_http", "sse"}:
            return await self._call_fastmcp_tool(server, tool_name, arguments or {})
        return await self._call_legacy_http_tool(server, tool_name, arguments or {})

    async def _list_legacy_http_tools(self, server: MCPServerConfig) -> list[dict[str, Any]]:
        url = server.endpoint.rstrip("/") + "/tools/list"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            return data.get("tools", data if isinstance(data, list) else [])

    async def _call_legacy_http_tool(
        self,
        server: MCPServerConfig,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> MCPToolResult:
        url = server.endpoint.rstrip("/") + "/tools/call"
        payload = {"tool_name": tool_name, "arguments": arguments or {}}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return MCPToolResult(
                    tool_name=tool_name,
                    server_name=server.name,
                    ok=bool(data.get("ok", True)),
                    result=data.get("result"),
                    error=data.get("error"),
                    metadata={"transport": server.transport, **(data.get("metadata", {}) or {})},
                )
        except Exception as exc:
            logger.exception("Erro ao chamar MCP tool %s em %s", tool_name, server.endpoint)
            return MCPToolResult(
                tool_name=tool_name,
                server_name=server.name,
                ok=False,
                error=str(exc),
                metadata={"transport": server.transport},
            )

    async def _open_fastmcp_session(self, server: MCPServerConfig):
        """Return an async context manager yielding an initialized MCP session."""
        try:
            from mcp import ClientSession
        except Exception as exc:  # pragma: no cover - depends on optional dependency
            raise RuntimeError(
                "FastMCP transport requires the optional package 'mcp'. "
                "Install with: pip install 'mcp>=1.9.0'"
            ) from exc

        if server.transport == "sse":
            try:
                from mcp.client.sse import sse_client
            except Exception as exc:  # pragma: no cover
                raise RuntimeError("MCP SSE client is unavailable in the installed mcp package") from exc

            class _SSESessionCM:
                async def __aenter__(self_inner):
                    self_inner.stream_cm = sse_client(server.endpoint, timeout=self.timeout_seconds)
                    read, write = await self_inner.stream_cm.__aenter__()
                    self_inner.session = ClientSession(read, write)
                    await self_inner.session.__aenter__()
                    await self_inner.session.initialize()
                    return self_inner.session

                async def __aexit__(self_inner, exc_type, exc, tb):
                    await self_inner.session.__aexit__(exc_type, exc, tb)
                    await self_inner.stream_cm.__aexit__(exc_type, exc, tb)

            return _SSESessionCM()

        try:
            from mcp.client.streamable_http import streamablehttp_client
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("MCP streamable HTTP client is unavailable in the installed mcp package") from exc

        class _StreamableHTTPSessionCM:
            async def __aenter__(self_inner):
                self_inner.stream_cm = streamablehttp_client(server.endpoint, timeout=self.timeout_seconds)
                streams = await self_inner.stream_cm.__aenter__()
                # Newer mcp returns (read, write, get_session_id); older returns (read, write).
                read, write = streams[0], streams[1]
                self_inner.session = ClientSession(read, write)
                await self_inner.session.__aenter__()
                await self_inner.session.initialize()
                return self_inner.session

            async def __aexit__(self_inner, exc_type, exc, tb):
                await self_inner.session.__aexit__(exc_type, exc, tb)
                await self_inner.stream_cm.__aexit__(exc_type, exc, tb)

        return _StreamableHTTPSessionCM()

    @staticmethod
    def _maybe_json(value: Any) -> Any:
        """Best-effort JSON decoding for MCP TextContent payloads.

        FastMCP commonly serializes Python dict/list tool returns as TextContent.text.
        The rest of the framework expects the legacy internal contract where
        ``MCPToolResult.result`` is already a Python object.  Without this
        normalization the agent runtime may treat a successful FastMCP call as
        unusable and fall back to a generic service-unavailable answer.
        """
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return value
        if not (text.startswith("{") or text.startswith("[")):
            return value
        try:
            return json.loads(text)
        except Exception:
            return value

    @classmethod
    def _content_to_python(cls, content: Any) -> Any:
        if content is None:
            return None

        # Pydantic models used by the MCP SDK/FastMCP.
        if hasattr(content, "model_dump"):
            dumped = content.model_dump(exclude_none=True)
            if dumped.get("type") == "text" and "text" in dumped:
                return cls._maybe_json(dumped["text"])
            if "text" in dumped and len(dumped) <= 3:
                return cls._maybe_json(dumped.get("text"))
            return dumped

        # TextContent-like objects.
        if hasattr(content, "text"):
            return cls._maybe_json(getattr(content, "text"))

        if isinstance(content, dict):
            if content.get("type") == "text" and "text" in content:
                return cls._maybe_json(content["text"])
            return {k: cls._content_to_python(v) for k, v in content.items()}

        if not isinstance(content, list):
            return cls._maybe_json(content)

        out: list[Any] = [cls._content_to_python(item) for item in content]
        if len(out) == 1:
            return out[0]
        return out

    @classmethod
    def _normalize_fastmcp_call_response(cls, response: Any) -> tuple[bool, Any, str | None, dict[str, Any]]:
        """Normalize official MCP CallToolResult into the framework contract.

        Official MCP/FastMCP returns a CallToolResult, generally with
        ``content=[TextContent(text='...')]`` and ``isError``.  Legacy framework
        MCP servers return ``{ok, result, error, metadata}``.  This method
        accepts both shapes and always returns ``(ok, result, error, metadata)``.
        """
        metadata: dict[str, Any] = {}
        is_error = bool(getattr(response, "isError", False) or getattr(response, "is_error", False))

        # Prefer structured content when available because it preserves dicts.
        structured = (
            getattr(response, "structuredContent", None)
            or getattr(response, "structured_content", None)
        )
        if structured is not None:
            payload = cls._content_to_python(structured)
        else:
            payload = cls._content_to_python(getattr(response, "content", response))

        # If the server/client already returned the framework legacy envelope, unwrap it.
        if isinstance(payload, dict) and ("ok" in payload or "result" in payload or "error" in payload):
            ok = bool(payload.get("ok", not bool(payload.get("error"))))
            result = payload.get("result", payload)
            error = payload.get("error")
            meta = payload.get("metadata")
            if isinstance(meta, dict):
                metadata.update(meta)
            return ok and not is_error, result, str(error) if error else None, metadata

        error = str(payload) if is_error else None
        return not is_error, payload, error, metadata

    async def _list_fastmcp_tools(self, server: MCPServerConfig) -> list[dict[str, Any]]:
        cm = await self._open_fastmcp_session(server)
        async with cm as session:
            response = await session.list_tools()
            tools = getattr(response, "tools", response)
            result = []
            for tool in tools or []:
                if hasattr(tool, "model_dump"):
                    data = tool.model_dump(exclude_none=True)
                else:
                    data = dict(tool)
                result.append({
                    "name": data.get("name"),
                    "description": data.get("description", ""),
                    "input_schema": data.get("inputSchema") or data.get("input_schema") or {},
                })
            return result

    async def _call_fastmcp_tool(
        self,
        server: MCPServerConfig,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> MCPToolResult:
        try:
            cm = await self._open_fastmcp_session(server)
            async with cm as session:
                # Load the tool list in the current MCP session before calling a tool.
                # Some MCP/FastMCP SDK versions keep the validation cache per session.
                # Without this, the call may still work, but the server/client emits:
                # "Tool '<name>' not listed, no validation will be performed".
                try:
                    listed_response = await session.list_tools()
                    listed_tools = getattr(listed_response, "tools", listed_response) or []
                    listed_names = []
                    for item in listed_tools:
                        if hasattr(item, "name"):
                            listed_names.append(getattr(item, "name"))
                        elif isinstance(item, dict):
                            listed_names.append(item.get("name"))
                    logger.info(
                        "fastmcp.tools.listed server=%s endpoint=%s tools=%s",
                        server.name,
                        server.endpoint,
                        [name for name in listed_names if name],
                    )
                    if listed_names and tool_name not in listed_names:
                        logger.warning(
                            "fastmcp.tool_not_declared tool=%s server=%s listed_tools=%s",
                            tool_name,
                            server.name,
                            [name for name in listed_names if name],
                        )
                except Exception:
                    # Do not fail the business call only because the discovery/list step failed.
                    logger.exception(
                        "fastmcp.tools.list_failed server=%s endpoint=%s; calling tool without validation cache",
                        server.name,
                        server.endpoint,
                    )

                response = await session.call_tool(tool_name, arguments=arguments or {})
                ok, payload, error, response_metadata = self._normalize_fastmcp_call_response(response)
                logger.info(
                    "fastmcp.tool_call.normalized tool=%s server=%s ok=%s result_type=%s error=%s",
                    tool_name,
                    server.name,
                    ok,
                    type(payload).__name__,
                    error,
                )
                return MCPToolResult(
                    tool_name=tool_name,
                    server_name=server.name,
                    ok=ok,
                    result=payload,
                    error=error,
                    metadata={
                        "transport": server.transport,
                        "endpoint": server.endpoint,
                        **response_metadata,
                    },
                )
        except Exception as exc:
            logger.exception("Erro ao chamar FastMCP tool %s em %s", tool_name, server.endpoint)
            return MCPToolResult(
                tool_name=tool_name,
                server_name=server.name,
                ok=False,
                error=str(exc),
                metadata={"transport": server.transport, "endpoint": server.endpoint},
            )
