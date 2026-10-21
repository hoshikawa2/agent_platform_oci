from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "agent-gateway-global-supervisor"
    APP_ENV: str = "local"
    LOG_LEVEL: str = "INFO"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8010
    CORS_ORIGINS: str = "http://localhost:5173"

    ENABLE_A2A: bool = False
    A2A_TASK_MODE: bool = True
    A2A_TASK_TIMEOUT_SECONDS: float = Field(default=120.0, gt=0)
    A2A_PUBLIC_URL: str = "http://localhost:8010"
    A2A_SECURITY_SCHEMES: dict = Field(default_factory=dict)
    A2A_SECURITY: list[dict[str, list[str]]] = Field(default_factory=list)

    BACKENDS_CONFIG_PATH: str = "./config/backends.yaml"
    GLOBAL_ROUTING_MODE: Literal["router", "supervisor", "hybrid"] = "hybrid"
    GLOBAL_KEEP_ACTIVE_BACKEND: bool = True
    GLOBAL_USE_SUPERVISOR_ON_CONFLICT: bool = True
    GLOBAL_MIN_ROUTER_CONFIDENCE: float = 0.55
    GLOBAL_SESSION_TTL_SECONDS: int = 3600
    BACKEND_TIMEOUT_SECONDS: float = 120.0

    # Reusa o provider do framework para o supervisor LLM.
    LLM_PROVIDER: Literal["mock", "oci_openai", "oci_sdk", "openai_compatible"] = "mock"
    LLM_TEMPERATURE: float = 0.0
    LLM_MAX_TOKENS: int = 700
    LLM_TIMEOUT_SECONDS: int = 60
    OCI_GENAI_BASE_URL: str = "https://inference.generativeai.sa-saopaulo-1.oci.oraclecloud.com/openai/v1"
    OCI_GENAI_MODEL: str = "openai.gpt-4.1"
    OCI_GENAI_API_KEY: str | None = None
    ENABLE_LANGFUSE: bool = False
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"
    MODEL_PRICES_JSON: str | None = None
    USD_BRL_RATE: str = "5.0"

    # Analytics/Observer do próprio gateway.
    ENABLE_ANALYTICS: bool = False
    ANALYTICS_PROVIDERS: str = "oci_streaming"
    GCP_PUBSUB_TOPIC_PATH: str | None = None
    AGENT_PUBSUB_TOPIC: str | None = None
    GCP_PROJECT_ID: str | None = None
    GCP_PUBSUB_TOPIC: str | None = None
    GCP_PUBSUB_TIMEOUT_SECONDS: float = 30.0
    ANALYTICS_FAIL_SILENT: bool = True
    ENABLE_OCI_STREAMING: bool = False
    OCI_STREAM_ENDPOINT: str | None = None
    OCI_STREAM_OCID: str | None = None
    OCI_STREAM_PARTITION_KEY: str = "agent-gateway-events"


@lru_cache
def get_settings() -> GatewaySettings:
    return GatewaySettings()


settings = get_settings()
