from __future__ import annotations

import logging
import os
from typing import Any

from .base import LLMProvider
from .types import LLMResponse
from .profile_resolver import LLMProfileResolver
from agent_framework.observability.token_cost import TokenUsageCollector
from agent_framework.billing.usage_repository import UsageRepository, UsageRecord

logger = logging.getLogger("agent_framework.llm")


def _normalize_generation_name(telemetry: Any, name: str, metadata: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    """Apply the observability contract before an LLM call reaches any tracer.

    This is deliberately done at the provider boundary as well as inside
    Telemetry.  Guardrail/judge calls supply semantic generation names such as
    ``guardrail.dlex_in``.  Normalizing here prevents alternate instrumentation
    paths (including provider wrappers) from observing an unmapped name.
    """
    meta = dict(metadata or {})
    mapper = getattr(telemetry, "code_mapper", None) if telemetry is not None else None
    if mapper is None or not hasattr(mapper, "normalize_name"):
        return str(name), meta
    return mapper.normalize_name(str(name), meta)


def _coerce_reasoning_text(value: Any) -> str | None:
    """Normalize provider-specific reasoning payloads without inventing content."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, (list, tuple)):
        chunks: list[str] = []
        for item in value:
            if isinstance(item, str):
                text = item
            else:
                text = getattr(item, "text", None) or getattr(item, "content", None)
                if text is None and isinstance(item, dict):
                    text = item.get("text") or item.get("content")
            if text:
                chunks.append(str(text))
        joined = "".join(chunks).strip()
        return joined or None
    if isinstance(value, dict):
        for key in ("content", "text", "reasoning_content", "reasoning"):
            text = _coerce_reasoning_text(value.get(key))
            if text:
                return text
        return None
    text = str(value).strip()
    return text or None


def _coerce_message_content(value: Any) -> str:
    """Normalize OpenAI-compatible message content without using reasoning as answer.

    OpenAI-compatible implementations may expose ``message.content`` as a plain
    string, a list of content parts, or SDK objects/dicts containing ``text``.
    Unknown shapes fail closed to an empty string instead of serializing the raw
    response object into the assistant answer.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        chunks: list[str] = []
        for item in value:
            if isinstance(item, str):
                chunks.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    chunks.append(text)
                continue
            text = getattr(item, "text", None)
            if isinstance(text, str):
                chunks.append(text)
        return "".join(chunks)
    if isinstance(value, dict):
        text = value.get("text")
        return text if isinstance(text, str) else ""
    text = getattr(value, "text", None)
    return text if isinstance(text, str) else ""


def _extract_openai_message_content(message: Any) -> str:
    if message is None:
        return ""
    if isinstance(message, dict):
        return _coerce_message_content(message.get("content"))
    return _coerce_message_content(getattr(message, "content", None))


def _extract_finish_reason(choice: Any) -> str | None:
    if choice is None:
        return None
    value = choice.get("finish_reason") if isinstance(choice, dict) else getattr(choice, "finish_reason", None)
    return str(value) if value is not None else None


def _extract_reasoning_content(obj: Any) -> str | None:
    """Best-effort extraction across OpenAI-compatible and OCI response shapes."""
    if obj is None:
        return None

    for attr in ("reasoning_content", "reasoning"):
        text = _coerce_reasoning_text(getattr(obj, attr, None))
        if text:
            return text

    if isinstance(obj, dict):
        for key in ("reasoning_content", "reasoning"):
            text = _coerce_reasoning_text(obj.get(key))
            if text:
                return text

    extra = getattr(obj, "model_extra", None)
    if isinstance(extra, dict):
        for key in ("reasoning_content", "reasoning"):
            text = _coerce_reasoning_text(extra.get(key))
            if text:
                return text

    return None


def _clean_config_value(value: Any) -> str | None:
    """Normalize values loaded from .env/YAML/PowerShell.

    Removes accidental quotes/apostrophes and surrounding whitespace, which
    otherwise may become URL-encoded as %27/%22 in OCI request endpoints.
    """
    if value is None:
        return None
    value = str(value).strip().strip("'\"").strip()
    return value or None




def _reasoning_enabled_for_model(*, provider: str, model: str | None, mode: str | None) -> bool:
    """Resolve whether reasoning_effort should be sent for this provider/model.

    Default mode is ``auto``. Auto is intentionally conservative: only known
    reasoning-capable model families are enabled. Operators may override with
    true/false through LLM_REASONING_ENABLED or an explicit invocation kwarg.
    """
    normalized_mode = str(mode or "auto").strip().lower()
    if normalized_mode in {"false", "0", "no", "off"}:
        return False
    if normalized_mode in {"true", "1", "yes", "on"}:
        return True

    model_name = (_clean_config_value(model) or "").lower()
    provider_name = str(provider or "").strip().lower()

    # OCI native SDK currently exposes reasoning_effort on GenericChatRequest,
    # but not every OCI-hosted model/endpoint accepts it. Keep auto allowlisted.
    if provider_name == "oci_sdk":
        return model_name.startswith(("openai.gpt-oss", "gpt-oss"))

    # OpenAI-compatible paths can support reasoning models depending on endpoint.
    if provider_name in {"oci_openai", "openai_compatible"}:
        return model_name.startswith((
            "openai.gpt-oss", "gpt-oss",
            "openai.gpt-5", "gpt-5",
            "openai.o1", "openai.o3", "openai.o4",
            "o1", "o3", "o4",
        ))

    return False

def _validate_openai_base_url(base_url: str | None, *, provider: str) -> str:
    cleaned = _clean_config_value(base_url)
    if not cleaned:
        raise RuntimeError(
            f"OCI_GENAI_BASE_URL é obrigatório para LLM_PROVIDER={provider}. "
            "Para OpenAI-compatible, use o endpoint terminando com /openai/v1."
        )
    cleaned = cleaned.rstrip('/')
    if '/openai/v1' not in cleaned:
        raise RuntimeError(
            f"Endpoint inválido para LLM_PROVIDER={provider}: {cleaned}. "
            "OCI_GENAI_BASE_URL precisa conter/terminar com /openai/v1."
        )
    return cleaned


def _validate_oci_sdk_base_url(base_url: str | None) -> str:
    cleaned = _clean_config_value(base_url)
    if not cleaned:
        raise RuntimeError(
            "OCI_GENAI_BASE_URL é obrigatório para LLM_PROVIDER=oci_sdk. "
            "Use apenas o endpoint nativo/privado base, sem /openai/v1, /20231130 ou /actions/chat."
        )
    cleaned = cleaned.rstrip('/')
    forbidden = ('/openai/v1', '/actions/chat', '/20231130', '/20240531')
    if any(x in cleaned for x in forbidden):
        raise RuntimeError(
            f"Endpoint inválido para LLM_PROVIDER=oci_sdk: {cleaned}. "
            "Para OCI SDK use apenas o host/base do endpoint, por exemplo "
            "https://<private-dedicated-genai-endpoint>. O SDK monta /20231130/actions/chat automaticamente."
        )
    return cleaned


class MockLLMProvider(LLMProvider):
    def __init__(self, settings=None, telemetry=None, usage_repository: UsageRepository | None = None):
        self.settings = settings
        self.telemetry = telemetry
        self.usage_repository = usage_repository
        self.model = "mock-llm"

    async def ainvoke(self, messages, **kwargs):
        return (await self.ainvoke_response(messages, **kwargs)).content

    async def ainvoke_response(self, messages, **kwargs):
        profile_name = kwargs.get("profile_name", "default")
        component_name = kwargs.get("component_name") or kwargs.get("component") or profile_name or "default"
        generation_name = kwargs.get("generation_name") or f"llm.{component_name}"
        generation_name, generation_mapping_meta = _normalize_generation_name(self.telemetry, generation_name)
        model = kwargs.get("model") or self.model
        profile_source = kwargs.get("profile_source")
        profile_found = kwargs.get("profile_found")
        profiles_enabled = kwargs.get("profiles_enabled")
        profiles_path = kwargs.get("profiles_path")
        llm_metadata = {"provider": "mock", "profile_name": profile_name, "component": component_name, "model": model, "profile_source": profile_source, "profile_found": profile_found, "profiles_enabled": profiles_enabled, "profiles_path": profiles_path, **generation_mapping_meta}
        async with _maybe_generation(
            self.telemetry,
            name=generation_name,
            model=model,
            input=messages,
            metadata=llm_metadata,
            model_parameters={},
        ) as generation:
            last = messages[-1].get("content", "") if messages else ""
            answer = f"[mock-llm] Resposta simulada para: {last[:300]}"
            usage = {"prompt_tokens": max(1, len(str(messages))//4), "completion_tokens": max(1, len(answer)//4), "total_tokens": max(2, (len(str(messages))+len(answer))//4), "cost_usd": 0.0, "cost_brl": 0.0}
            generation.set_output(answer)
            generation.set_usage(usage)
            generation.set_metadata(**usage)
        if self.usage_repository:
            await self.usage_repository.record(UsageRecord.from_usage("mock", model, generation_name, usage, llm_metadata))
        return LLMResponse(
            content=answer,
            reasoning_content=None,
            provider="mock",
            model=model,
            profile_name=profile_name,
            usage=dict(usage),
            metadata=dict(llm_metadata),
        )


class OCICompatibleOpenAIProvider(LLMProvider):
    """Provider principal: OCI Generative AI via endpoint OpenAI-compatible.

    Also supports optional dynamic per-inference profiles from llm_profiles.yaml.
    If the YAML file does not exist, behavior remains .env based as before.
    """

    def __init__(self, settings, telemetry=None, usage_repository: UsageRepository | None = None):
        self.settings = settings
        self.telemetry = telemetry
        self.usage_repository = usage_repository
        self.profile_resolver = LLMProfileResolver.from_settings(settings)
        self.provider_name = getattr(settings, "LLM_PROVIDER", "oci_openai")
        self.model = settings.OCI_GENAI_MODEL
        self.temperature = settings.LLM_TEMPERATURE
        self.max_tokens = settings.LLM_MAX_TOKENS
        self.token_collector = TokenUsageCollector(settings)
        self._clients: dict[tuple[str | None, str | None, float | int | None, bool], Any] = {}

        if self.provider_name in ("oci_openai", "openai_compatible"):
            settings.OCI_GENAI_BASE_URL = _validate_openai_base_url(
                getattr(settings, "OCI_GENAI_BASE_URL", None),
                provider=self.provider_name,
            )

        if not settings.OCI_GENAI_API_KEY and self.provider_name not in ("mock",):
            raise RuntimeError(
                "OCI_GENAI_API_KEY não configurado. "
                "Defina LLM_PROVIDER=oci_openai e OCI_GENAI_API_KEY no .env."
            )

        # Eagerly create the env/default client to preserve current startup behavior
        # for real OpenAI-compatible providers. In mock mode, do not require any API key.
        self.client = None
        if self.provider_name != 'mock':
            self.client = self._get_client(
                base_url=settings.OCI_GENAI_BASE_URL,
                api_key=settings.OCI_GENAI_API_KEY,
                timeout=settings.LLM_TIMEOUT_SECONDS,
            )

        logger.info(
            "LLM provider inicializado provider=%s base_url=%s model=%s langfuse=%s profiles_enabled=%s",
            self.provider_name,
            settings.OCI_GENAI_BASE_URL,
            self.model,
            bool(getattr(settings, "ENABLE_LANGFUSE", False)),
            self.profile_resolver.enabled,
        )

    def _resolve_async_openai(self, settings):
        # The framework records LLM calls through Telemetry.generation(...), where
        # we can inject the request trace_context. The langfuse.openai wrapper is
        # useful in simple apps, but in this framework it may create one top-level
        # Langfuse trace per OpenAI call when no parent observation is active in
        # the SDK context. Keep it opt-in to avoid noisy trace lists.
        use_langfuse_wrapper = str(
            getattr(settings, "ENABLE_LANGFUSE_OPENAI_AUTO_INSTRUMENTATION", None)
            or os.getenv("ENABLE_LANGFUSE_OPENAI_AUTO_INSTRUMENTATION", "false")
        ).strip().lower() in {"1", "true", "yes", "on", "y"}

        # The framework owns Langfuse correlation.  Even compatibility paths may
        # instantiate a provider without passing ``Telemetry`` explicitly while a
        # request is already active (for example GuardrailLLMClient running in its
        # sync bridge).  In that situation langfuse.openai would auto-create an
        # ``OpenAI-generation`` root trace instead of attaching to the business
        # request.  Treat an active framework observability context exactly like
        # an injected Telemetry instance and keep the standard OpenAI client.
        active_framework_trace = False
        try:
            from agent_framework.observability.context import get_observability_context

            obs_ctx = get_observability_context()
            active_framework_trace = bool(obs_ctx.trace_id or obs_ctx.request_id)
        except Exception:
            active_framework_trace = False

        if use_langfuse_wrapper and (self.telemetry is not None or active_framework_trace):
            logger.warning(
                "ENABLE_LANGFUSE_OPENAI_AUTO_INSTRUMENTATION=true ignorado durante execução correlacionada "
                "do framework; langfuse.openai pode criar OpenAI-generation como trace raiz separado."
            )
            use_langfuse_wrapper = False
        if getattr(settings, "ENABLE_LANGFUSE", False) and use_langfuse_wrapper:
            try:
                from langfuse.openai import AsyncOpenAI
                return AsyncOpenAI
            except Exception:
                logger.exception(
                    "Langfuse OpenAI auto-instrumentation habilitada, mas langfuse.openai.AsyncOpenAI "
                    "não pôde ser importado. Usando openai.AsyncOpenAI sem auto-instrumentação."
                )
        from openai import AsyncOpenAI
        return AsyncOpenAI

    def _get_client(self, *, base_url: str | None, api_key: str | None, timeout: float | int | None):
        key = (base_url, api_key, timeout, bool(getattr(self.settings, "ENABLE_LANGFUSE", False)))
        if key not in self._clients:
            AsyncOpenAI = self._resolve_async_openai(self.settings)
            self._clients[key] = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
        return self._clients[key]

    async def ainvoke(self, messages, **kwargs):
        return (await self.ainvoke_response(messages, **kwargs)).content

    async def ainvoke_response(self, messages, **kwargs):
        profile_name = kwargs.pop("profile_name", None)
        component_name = kwargs.pop("component_name", None) or kwargs.pop("component", None) or profile_name or "default"
        generation_name = kwargs.pop("generation_name", None) or f"llm.{component_name}"
        generation_name, generation_mapping_meta = _normalize_generation_name(self.telemetry, generation_name)
        effective = self.profile_resolver.resolve(profile_name, **kwargs)
        provider = str(effective.get("provider") or self.provider_name)
        model = str(effective.get("model") or self.model)
        temperature = effective.get("temperature", self.temperature)
        max_tokens = effective.get("max_tokens", self.max_tokens)
        timeout = effective.get("timeout_seconds", getattr(self.settings, "LLM_TIMEOUT_SECONDS", 120))
        base_url = _clean_config_value(effective.get("base_url") or getattr(self.settings, "OCI_GENAI_BASE_URL", None))
        api_key = _clean_config_value(effective.get("api_key") or getattr(self.settings, "OCI_GENAI_API_KEY", None))
        resolved_profile_name = effective.get("profile_name") or profile_name or "default"
        requested_profile_name = effective.get("requested_profile_name") or profile_name or "default"
        profile_source = effective.get("profile_source") or ("yaml" if effective.get("profiles_enabled") else "env")
        profile_found = bool(effective.get("profile_found"))
        component_name = str(component_name or resolved_profile_name)

        if provider == "mock":
            mock = MockLLMProvider(self.settings, telemetry=self.telemetry, usage_repository=self.usage_repository)
            return await mock.ainvoke_response(
                messages,
                model=model,
                profile_name=resolved_profile_name,
                component_name=component_name,
                generation_name=generation_name,
                profile_source=profile_source,
                profile_found=profile_found,
                profiles_enabled=bool(effective.get("profiles_enabled")),
                profiles_path=effective.get("profiles_path"),
            )

        if provider == "oci_sdk":
            sdk = OCISDKProvider(self.settings, telemetry=self.telemetry, usage_repository=self.usage_repository)
            return await sdk.ainvoke_response(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout_seconds=timeout,
                compartment_id=effective.get("compartment_id") or effective.get("project_ocid"),
                # Regra do framework: OCI_GENAI_BASE_URL é usado em todos os providers.
                # Para oci_sdk ele deve ser apenas o service endpoint base, sem /openai/v1.
                endpoint=(
                        effective.get("base_url")
                        or effective.get("service_endpoint")
                        or effective.get("endpoint")
                        or getattr(self.settings, "OCI_GENAI_BASE_URL", None)
                ),
                # Regra do framework: em oci_sdk, OCI_GENAI_MODEL representa o endpoint_id
                # quando o valor é um ocid1.generativeaiendpoint...
                endpoint_id=(
                        effective.get("endpoint_id")
                        or effective.get("dedicated_endpoint_id")
                        or model
                ),
                profile_name=resolved_profile_name,
                requested_profile_name=requested_profile_name,
                profile_source=profile_source,
                profile_found=profile_found,
                profiles_enabled=bool(effective.get("profiles_enabled")),
                profiles_path=effective.get("profiles_path"),
                component_name=component_name,
                generation_name=generation_name,
            )

        if provider not in ("oci_openai", "openai_compatible"):
            raise ValueError(f"LLM provider não suportado no profile {resolved_profile_name}: {provider}")

        base_url = _validate_openai_base_url(base_url, provider=provider)

        if not api_key:
            raise RuntimeError(
                f"API key ausente para o profile LLM {resolved_profile_name!r}. "
                "Configure api_key no llm_profiles.yaml ou OCI_GENAI_API_KEY no .env."
            )

        client = self._get_client(base_url=base_url, api_key=api_key, timeout=timeout)

        request_kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        # Optional OpenAI-compatible params. Only send when explicitly configured.
        for optional_key in ("top_p", "frequency_penalty", "presence_penalty"):
            if effective.get(optional_key) is not None:
                request_kwargs[optional_key] = effective[optional_key]
        model_parameters = {
            key: value
            for key, value in request_kwargs.items()
            if key not in {"model", "messages"} and value is not None
        }
        llm_metadata = {
            "provider": provider,
            "model": model,
            "component": component_name,
            "profile_name": resolved_profile_name,
            "requested_profile_name": requested_profile_name,
            "profile_source": profile_source,
            "profile_found": profile_found,
            "profiles_enabled": bool(effective.get("profiles_enabled")),
            "profiles_path": effective.get("profiles_path"),
            **generation_mapping_meta,
        }

        async with _maybe_span(
                self.telemetry,
                "llm.chat_completion",
                provider=provider,
                model=model,
                profile_name=resolved_profile_name,
                requested_profile_name=requested_profile_name,
                profile_source=profile_source,
                profile_found=profile_found,
                component=component_name,
                temperature=temperature,
                max_tokens=max_tokens,
                profiles_enabled=bool(effective.get("profiles_enabled")),
        ):
            try:
                async with _maybe_generation(
                    self.telemetry,
                    name=generation_name,
                    model=model,
                    input=messages,
                    metadata=llm_metadata,
                    model_parameters=model_parameters,
                ) as generation:
                    resp = await client.chat.completions.create(**request_kwargs)
                    choices = getattr(resp, "choices", None) or []
                    if not choices:
                        message = None
                        answer = ""
                        reasoning_content = None
                        finish_reason = None
                        logger.warning(
                            "OpenAI-compatible LLM returned no choices provider=%s model=%s profile=%s component=%s",
                            provider, model, resolved_profile_name, component_name,
                        )
                    else:
                        choice = choices[0]
                        message = choice.get("message") if isinstance(choice, dict) else getattr(choice, "message", None)
                        answer = _extract_openai_message_content(message)
                        reasoning_content = _extract_reasoning_content(message)
                        finish_reason = _extract_finish_reason(choice)

                    logger.info(
                        "OpenAI-compatible LLM response provider=%s model=%s profile=%s component=%s "
                        "finish_reason=%s content_len=%d reasoning_len=%d",
                        provider, model, resolved_profile_name, component_name,
                        finish_reason, len(answer), len(reasoning_content or ""),
                    )

                    usage_metadata = self.token_collector.enrich(model, getattr(resp, "usage", None))
                    usage_metadata.update({
                        "profile_name": resolved_profile_name,
                        "requested_profile_name": requested_profile_name,
                        "profile_source": profile_source,
                        "profile_found": profile_found,
                        "component": component_name,
                        "model": model,
                        "provider": provider,
                        "finish_reason": finish_reason,
                        "content_length": len(answer),
                        "reasoning_content_length": len(reasoning_content or ""),
                        **model_parameters,
                    })
                    llm_metadata.update({
                        "finish_reason": finish_reason,
                        "content_length": len(answer),
                        "reasoning_content_length": len(reasoning_content or ""),
                    })
                    generation.set_output(answer)
                    generation.set_usage(usage_metadata)
                    generation.set_metadata(**usage_metadata)
                if self.usage_repository:
                    await self.usage_repository.record(
                        UsageRecord.from_usage(provider, model, generation_name, usage_metadata, llm_metadata)
                    )

                return LLMResponse(
                    content=answer,
                    reasoning_content=reasoning_content,
                    provider=provider,
                    model=model,
                    profile_name=resolved_profile_name,
                    usage=dict(usage_metadata),
                    metadata=dict(llm_metadata),
                )
            except Exception as exc:
                logger.exception(
                    "Erro ao chamar LLM provider=%s component=%s profile=%s model=%s: %s",
                    provider,
                    component_name,
                    resolved_profile_name,
                    model,
                    exc,
                )
                raise

    async def aclose(self) -> None:
        """Close all cached OpenAI-compatible clients inside their owning event loop.

        Temporary providers are created by legacy guardrail compatibility bridges.
        Explicitly closing them before ``asyncio.run`` returns prevents the OpenAI/httpx
        client finalizer from trying to close transports after the loop is already gone.
        Persistent application-owned providers can call the same method at shutdown.
        """
        clients = list(self._clients.values())
        self._clients.clear()
        self.client = None
        for client in clients:
            close = getattr(client, "close", None)
            aclose = getattr(client, "aclose", None)
            try:
                if callable(aclose):
                    result = aclose()
                    if hasattr(result, "__await__"):
                        await result
                elif callable(close):
                    result = close()
                    if hasattr(result, "__await__"):
                        await result
            except Exception:
                logger.exception("Erro ao fechar cliente OpenAI-compatible")

    def _using_langfuse_openai(self) -> bool:
        if self.client is None:
            return False
        module = self.client.__class__.__module__
        return "langfuse" in module


class OpenAICompatibleProvider(OCICompatibleOpenAIProvider):
    """Provider genérico OpenAI-compatible.

    Reusa as variáveis OCI_GENAI_* para manter compatibilidade com o template,
    mas permite apontar para outro endpoint OpenAI-compatible.
    """

    def __init__(self, settings, telemetry=None, usage_repository: UsageRepository | None = None):
        super().__init__(settings, telemetry=telemetry, usage_repository=usage_repository)
        self.provider_name = "openai_compatible"


class OCISDKProvider(LLMProvider):
    """OCI Generative AI via OCI Python SDK.

    Supports:
    - Public regional endpoint
    - Private/dedicated service endpoint
    - OnDemandServingMode(model_id=...)
    - DedicatedServingMode(endpoint_id=...)
    """

    def __init__(self, settings, telemetry=None, usage_repository: UsageRepository | None = None):
        self.settings = settings
        self.telemetry = telemetry
        self.usage_repository = usage_repository
        self.model = settings.OCI_GENAI_MODEL
        self.token_collector = TokenUsageCollector(settings)
        self._clients: dict[str, Any] = {}

    @staticmethod
    def _normalize_endpoint(endpoint: str | None) -> str | None:
        # Para oci_sdk, OCI_GENAI_BASE_URL é obrigatório e deve ser apenas o host/base.
        return _validate_oci_sdk_base_url(endpoint)

    @classmethod
    def _resolve_endpoint(cls, settings, endpoint: str | None = None) -> str:
        # Regra do framework: OCI_GENAI_BASE_URL é o parâmetro único de endpoint
        # também para o OCI SDK. Não usa OCI_GENAI_ENDPOINT como fonte principal.
        configured = endpoint or getattr(settings, "OCI_GENAI_BASE_URL", None)
        return cls._normalize_endpoint(configured)

    def _get_client(self, endpoint: str | None = None):
        resolved_endpoint = self._resolve_endpoint(self.settings, endpoint)

        if resolved_endpoint not in self._clients:
            from oci.generative_ai_inference import GenerativeAiInferenceClient
            from agent_framework.oci.auth import get_oci_config_and_signer

            config, signer = get_oci_config_and_signer(self.settings)

            kwargs = {
                "config": config,
                "service_endpoint": resolved_endpoint,
            }

            if signer is not None:
                kwargs["signer"] = signer

            self._clients[resolved_endpoint] = GenerativeAiInferenceClient(**kwargs)

            logger.info(
                "OCI SDK GenAI client inicializado service_endpoint=%s auth_mode=%s",
                resolved_endpoint,
                getattr(self.settings, "OCI_AUTH_MODE", "config_file"),
            )

        return self._clients[resolved_endpoint]

    @staticmethod
    def _to_prompt(messages) -> str:
        parts: list[str] = []
        for m in messages or []:
            role = (m.get("role") if isinstance(m, dict) else getattr(m, "role", "user")) or "user"
            content = (m.get("content") if isinstance(m, dict) else getattr(m, "content", "")) or ""
            parts.append(f"{role}: {content}")
        return "\n".join(parts)

    def _build_serving_mode(self, *, model: str, endpoint_id: str | None):
        from oci.generative_ai_inference import models

        model = _clean_config_value(model) or ""
        endpoint_id = _clean_config_value(endpoint_id)

        # Regra do framework: para LLM_PROVIDER=oci_sdk, OCI_GENAI_MODEL pode ser
        # diretamente o ocid1.generativeaiendpoint... do endpoint dedicado.
        if endpoint_id and endpoint_id.startswith("ocid1.generativeaiendpoint."):
            if not hasattr(models, "DedicatedServingMode"):
                raise RuntimeError(
                    "OCI SDK instalado não possui DedicatedServingMode. "
                    "Atualize o pacote oci para usar endpoint dedicado."
                )

            logger.info("Usando OCI GenAI DedicatedServingMode endpoint_id=%s", endpoint_id)
            return models.DedicatedServingMode(endpoint_id=endpoint_id)

        # Fallback para on-demand, caso alguém use OCI_GENAI_MODEL como nome/model id.
        # Para dedicated endpoint, OCI_GENAI_MODEL deve começar com ocid1.generativeaiendpoint.
        logger.info("Usando OCI GenAI OnDemandServingMode model_id=%s", model)
        return models.OnDemandServingMode(model_id=model)

    def _build_chat_details(
            self,
            *,
            messages,
            model: str,
            endpoint_id: str | None,
            compartment_id: str,
            temperature: float,
            max_tokens: int,
            reasoning_effort: str | None = None,
    ):
        from oci.generative_ai_inference import models

        serving_mode = self._build_serving_mode(model=model, endpoint_id=endpoint_id)

        if hasattr(models, "GenericChatRequest") and hasattr(models, "UserMessage"):
            oci_messages = []

            for m in messages or []:
                role = (m.get("role") if isinstance(m, dict) else getattr(m, "role", "user")) or "user"
                content = (m.get("content") if isinstance(m, dict) else getattr(m, "content", "")) or ""

                if hasattr(models, "TextContent"):
                    content_payload = [models.TextContent(text=str(content))]
                else:
                    content_payload = str(content)

                if role == "system" and hasattr(models, "SystemMessage"):
                    oci_messages.append(models.SystemMessage(content=content_payload))
                elif role == "assistant" and hasattr(models, "AssistantMessage"):
                    oci_messages.append(models.AssistantMessage(content=content_payload))
                else:
                    oci_messages.append(models.UserMessage(content=content_payload))

            chat_request = models.GenericChatRequest(
                messages=oci_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            # gpt-oss reasoning budget. Only set when the SDK exposes the field
            # (older versions don't) so we never break the request building.
            if reasoning_effort and hasattr(chat_request, "reasoning_effort"):
                chat_request.reasoning_effort = str(reasoning_effort).upper()

            return models.ChatDetails(
                compartment_id=compartment_id,
                serving_mode=serving_mode,
                chat_request=chat_request,
            )

        prompt = self._to_prompt(messages)

        chat_request = models.CohereChatRequest(
            message=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return models.ChatDetails(
            compartment_id=compartment_id,
            serving_mode=serving_mode,
            chat_request=chat_request,
        )

    @staticmethod
    def _extract_answer(response) -> str:
        data = getattr(response, "data", response)
        chat_response = getattr(data, "chat_response", None) or data

        for attr in ("text", "message", "output_text"):
            value = getattr(chat_response, attr, None)
            if value:
                return str(value)

        choices = getattr(chat_response, "choices", None) or []
        if choices:
            first = choices[0]
            msg = getattr(first, "message", None)
            content = getattr(msg, "content", None) if msg is not None else getattr(first, "text", None)

            if isinstance(content, list):
                chunks = []
                for item in content:
                    chunks.append(str(getattr(item, "text", item)))
                return "".join(chunks)

            if content:
                return str(content)

            # Choices present but no content (e.g. a reasoning model that burned
            # its budget and stopped on finish_reason=length). Return "" — never
            # the raw response object — so callers see empty content and fail
            # cleanly instead of treating the serialized dump as the answer.
            return ""

        return str(chat_response)

    @staticmethod
    def _extract_reasoning_content(response) -> str | None:
        data = getattr(response, "data", response)
        chat_response = getattr(data, "chat_response", None) or data

        text = _extract_reasoning_content(chat_response)
        if text:
            return text

        choices = getattr(chat_response, "choices", None) or []
        if choices:
            first = choices[0]
            message = getattr(first, "message", None)
            return _extract_reasoning_content(message) or _extract_reasoning_content(first)
        return None

    async def ainvoke(self, messages, **kwargs):
        return (await self.ainvoke_response(messages, **kwargs)).content

    async def ainvoke_response(self, messages, **kwargs):
        import asyncio

        model = _clean_config_value(kwargs.get("model") or self.model)
        endpoint = _clean_config_value(kwargs.get("endpoint") or getattr(self.settings, "OCI_GENAI_BASE_URL", None))
        # Regra do framework: OCI_GENAI_MODEL é o endpoint_id quando for dedicated.
        endpoint_id = _clean_config_value(kwargs.get("endpoint_id") or model)

        temperature = kwargs.get("temperature", getattr(self.settings, "LLM_TEMPERATURE", 0.2))
        max_tokens = kwargs.get("max_tokens", getattr(self.settings, "LLM_MAX_TOKENS", 2048))
        configured_reasoning_effort = kwargs.get("reasoning_effort") or getattr(self.settings, "LLM_REASONING_EFFORT", None)
        reasoning_mode = kwargs.get("reasoning_enabled", getattr(self.settings, "LLM_REASONING_ENABLED", "auto"))
        reasoning_effort = (
            configured_reasoning_effort
            if configured_reasoning_effort and _reasoning_enabled_for_model(
                provider="oci_sdk", model=model, mode=reasoning_mode
            )
            else None
        )
        if configured_reasoning_effort and not reasoning_effort:
            logger.info(
                "reasoning_effort suppressed provider=oci_sdk model=%s mode=%s",
                model, reasoning_mode,
            )

        compartment_id = (
                kwargs.get("compartment_id")
                or getattr(self.settings, "OCI_COMPARTMENT_ID", None)
                or getattr(self.settings, "OCI_GENAI_PROJECT_OCID", None)
        )

        profile_name = kwargs.get("profile_name", "default")
        component_name = kwargs.get("component_name") or kwargs.get("component") or profile_name
        generation_name = kwargs.get("generation_name") or f"llm.{component_name}"
        generation_name, generation_mapping_meta = _normalize_generation_name(self.telemetry, generation_name)

        if not compartment_id:
            raise RuntimeError(
                "OCI_COMPARTMENT_ID or OCI_GENAI_PROJECT_OCID is required for LLM_PROVIDER=oci_sdk"
            )

        service_endpoint = self._resolve_endpoint(self.settings, endpoint)
        model_parameters = {
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        llm_metadata = {
            "provider": "oci_sdk",
            "model": model,
            "endpoint_id": endpoint_id,
            "service_endpoint": service_endpoint,
            "component": component_name,
            "profile_name": profile_name,
            "auth_mode": getattr(self.settings, "OCI_AUTH_MODE", "config_file"),
            **generation_mapping_meta,
        }

        async with _maybe_span(
                self.telemetry,
                "llm.chat_completion",
                provider="oci_sdk",
                model=model,
                endpoint_id=endpoint_id,
                service_endpoint=service_endpoint,
                profile_name=profile_name,
                component=component_name,
                auth_mode=getattr(self.settings, "OCI_AUTH_MODE", "config_file"),
                temperature=temperature,
                max_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
        ):
            client = self._get_client(service_endpoint)

            details = self._build_chat_details(
                messages=messages,
                model=model,
                endpoint_id=endpoint_id,
                compartment_id=compartment_id,
                temperature=temperature,
                max_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
            )

            async with _maybe_generation(
                self.telemetry,
                name=generation_name,
                model=model,
                input=messages,
                metadata=llm_metadata,
                model_parameters=model_parameters,
            ) as generation:
                response = await asyncio.to_thread(client.chat, details)
                answer = self._extract_answer(response)
                reasoning_content = self._extract_reasoning_content(response)

                usage_metadata = {
                    "prompt_tokens": max(1, len(str(messages)) // 4),
                    "completion_tokens": max(1, len(answer) // 4),
                    "total_tokens": max(2, (len(str(messages)) + len(answer)) // 4),
                    "cost_usd": 0.0,
                    "cost_brl": 0.0,
                    "estimated_usage": True,
                    **llm_metadata,
                    **model_parameters,
                }
                generation.set_output(answer)
                generation.set_usage(usage_metadata)
                generation.set_metadata(**usage_metadata)

            if self.usage_repository:
                await self.usage_repository.record(
                    UsageRecord.from_usage(
                        "oci_sdk",
                        model,
                        generation_name,
                        usage_metadata,
                        llm_metadata,
                    )
                )

            return LLMResponse(
                content=answer,
                reasoning_content=reasoning_content,
                provider="oci_sdk",
                model=model,
                profile_name=profile_name,
                usage=dict(usage_metadata),
                metadata=dict(llm_metadata),
            )


def create_llm(settings, telemetry=None, usage_repository: UsageRepository | None = None) -> LLMProvider:
    provider = settings.LLM_PROVIDER
    if provider == "oci_openai":
        return OCICompatibleOpenAIProvider(settings, telemetry=telemetry, usage_repository=usage_repository)
    if provider == "openai_compatible":
        return OpenAICompatibleProvider(settings, telemetry=telemetry, usage_repository=usage_repository)
    if provider == "oci_sdk":
        return OCISDKProvider(settings, telemetry=telemetry, usage_repository=usage_repository)
    if provider == "mock":
        # When llm_profiles.yaml exists, even an env mock backend may route specific
        # inference points to real providers. Use the dynamic provider in that case;
        # otherwise preserve the old lightweight mock behavior.
        resolver = LLMProfileResolver.from_settings(settings)
        if resolver.enabled:
            return OCICompatibleOpenAIProvider(settings, telemetry=telemetry, usage_repository=usage_repository)
        return MockLLMProvider(settings, telemetry=telemetry, usage_repository=usage_repository)
    raise ValueError(f"LLM_PROVIDER não suportado: {provider}")


class _maybe_span:
    def __init__(self, telemetry, name: str, **attrs: Any):
        self.telemetry = telemetry
        self.name = name
        self.attrs = attrs
        self.cm = None

    async def __aenter__(self):
        if not self.telemetry:
            return None
        self.cm = self.telemetry.span(self.name, **self.attrs)
        return await self.cm.__aenter__()

    async def __aexit__(self, exc_type, exc, tb):
        if self.cm:
            return await self.cm.__aexit__(exc_type, exc, tb)
        return False


class _NoopGeneration:
    def set_output(self, output: Any) -> None:
        pass

    def set_usage(self, usage: dict[str, Any] | None) -> None:
        pass

    def set_metadata(self, **metadata: Any) -> None:
        pass

    def set_model_parameters(self, **model_parameters: Any) -> None:
        pass


class _maybe_generation:
    def __init__(self, telemetry, **attrs: Any):
        self.telemetry = telemetry
        self.attrs = attrs
        self.cm = None
        self.noop = _NoopGeneration()

    async def __aenter__(self):
        if not self.telemetry or not hasattr(self.telemetry, "generation_span"):
            return self.noop
        self.cm = self.telemetry.generation_span(**self.attrs)
        return await self.cm.__aenter__()

    async def __aexit__(self, exc_type, exc, tb):
        if self.cm:
            return await self.cm.__aexit__(exc_type, exc, tb)
        return False
