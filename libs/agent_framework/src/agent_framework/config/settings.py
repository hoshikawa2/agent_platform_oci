from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env into os.environ as well.
# Pydantic Settings reads .env for Settings fields, but parts of the calibrated
# guardrails intentionally use os.getenv for compatibility with the original
# guardrails package. Loading here keeps both paths consistent.
load_dotenv(override=False)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    APP_NAME: str = 'ai-agent-template'
    APP_ENV: str = 'local'
    LOG_LEVEL: str = 'INFO'
    API_HOST: str = '0.0.0.0'
    API_PORT: int = 8000
    CORS_ORIGINS: str = 'http://localhost:5173'

    LLM_PROVIDER: Literal['mock','oci_openai','oci_sdk','openai_compatible'] = 'mock'
    LLM_TEMPERATURE: float = 0.2
    LLM_MAX_TOKENS: int = 2048
    LLM_TIMEOUT_SECONDS: int = 120
    LLM_PROFILES_PATH: str = './llm_profiles.yaml'

    OCI_GENAI_BASE_URL: str = 'https://inference.generativeai.sa-saopaulo-1.oci.oraclecloud.com/openai/v1'
    OCI_GENAI_MODEL: str = 'openai.gpt-4.1'
    OCI_GENAI_API_KEY: str | None = None
    OCI_GENAI_PROJECT_OCID: str | None = None
    # OCI SDK authentication mode.
    # config_file = ~/.oci/config profile (default/local development)
    # instance_principal = OCI Instance Principal signer (Compute/OKE without API key)
    # resource_principal = OCI Resource Principal signer (Functions/resource principal contexts)
    OCI_AUTH_MODE: Literal['config_file','instance_principal','resource_principal'] = 'config_file'
    OCI_CONFIG_FILE: str = '~/.oci/config'
    OCI_PROFILE: str = 'DEFAULT'
    OCI_COMPARTMENT_ID: str | None = None
    OCI_REGION: str = 'sa-saopaulo-1'
    OCI_GENAI_ENDPOINT: str | None = None
    OCI_EMBEDDING_ENDPOINT: str | None = None

    SESSION_REPOSITORY_PROVIDER: Literal['memory','sqlite','autonomous','oracle','mongodb'] = 'memory'
    MEMORY_REPOSITORY_PROVIDER: Literal['memory','sqlite','autonomous','oracle','mongodb'] = 'memory'
    CHECKPOINT_REPOSITORY_PROVIDER: Literal['memory','sqlite','autonomous','oracle','mongodb'] = 'memory'

    # ConversationSummaryMemory: compressão de contexto conversacional.
    # none    = não injeta histórico no prompt
    # window  = injeta somente últimas mensagens
    # summary = resumo acumulado + últimas mensagens completas
    ENABLE_CONVERSATION_SUMMARY_MEMORY: bool = False
    MEMORY_CONTEXT_STRATEGY: Literal['none','window','summary'] = 'window'
    MEMORY_HISTORY_LIMIT: int = 80
    MEMORY_RECENT_MESSAGES_LIMIT: int = 8
    MEMORY_SUMMARY_TRIGGER_MESSAGES: int = 20
    MEMORY_MAX_SUMMARY_CHARS: int = 6000
    MEMORY_SUMMARY_USE_LLM: bool = True
    MEMORY_INJECT_RECENT_MESSAGES: bool = True
    MEMORY_INJECT_SUMMARY: bool = True

    # LangGraph enterprise checkpointing
    ENABLE_RESILIENT_CHECKPOINTER: bool = True
    ENABLE_CHECKPOINT_INTEGRITY: bool = True
    ENABLE_CHECKPOINT_COMPACTION: bool = True
    CHECKPOINT_COMPACT_EVERY: int = 50
    CHECKPOINT_KEEP_LAST: int = 20
    CHECKPOINT_RECOVERY_SCAN_LIMIT: int = 25
    CHECKPOINT_RETRY_MAX_ATTEMPTS: int = 3
    CHECKPOINT_RETRY_BASE_DELAY_SECONDS: float = 0.05
    CHECKPOINT_RETRY_MAX_DELAY_SECONDS: float = 1.0
    CHECKPOINT_RETRY_JITTER_SECONDS: float = 0.05
    USAGE_REPOSITORY_PROVIDER: Literal['sqlite','autonomous','oracle'] = 'sqlite'

    ADB_USER: str | None = None
    ADB_PASSWORD: str | None = None
    ADB_DSN: str | None = None
    ADB_WALLET_LOCATION: str | None = None
    ADB_WALLET_PASSWORD: str | None = None
    ADB_TABLE_PREFIX: str = 'AGENTFW'

    MONGODB_URI: str = 'mongodb://localhost:27017'
    MONGODB_DATABASE: str = 'agent_platform'
    REDIS_URL: str = 'redis://localhost:6379/0'
    ENABLE_REDIS_CACHE: bool = False
    CACHE_KEY_PREFIX: str = 'agentfw'

    VECTOR_STORE_PROVIDER: Literal['memory','sqlite','autonomous','oracle','mongodb'] = 'memory'
    GRAPH_STORE_PROVIDER: Literal['memory','autonomous','oracle'] = 'memory'
    ORACLE_GRAPH_NAME: str = 'AGENTFW_GRAPH'
    ORACLE_GRAPH_AUTO_CREATE: bool = False
    RAG_TOP_K: int = 5
    ENABLE_RAG_QUERY_REWRITE: bool = False
    ENABLE_RAG_CONTEXT_COMPRESSION: bool = False
    ENABLE_RAG_GENERATION: bool = False
    EMBEDDING_PROVIDER: Literal['mock','oci'] = 'mock'
    OCI_EMBEDDING_MODEL: str = 'cohere.embed-multilingual-v3.0'

    ENABLE_LANGFUSE: bool = False
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_HOST: str = 'https://cloud.langfuse.com'
    MODEL_PRICES_JSON: str | None = None
    USD_BRL_RATE: str = '5.0'
    ENABLE_OTEL: bool = False
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None
    OTEL_SERVICE_NAME: str = 'ai-agent-template'
    # Dedicated NOC OpenTelemetry Logs channel. This is separate from trace/span OTel.
    ENABLE_NOC_OTEL_LOGS: bool = False
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT: str | None = None
    OTEL_EXPORTER_OTLP_HOST_HEADER: str | None = None

    ENABLE_ANALYTICS: bool = False
    ANALYTICS_PROVIDERS: str = 'oci_streaming'
    GCP_PUBSUB_TOPIC_PATH: str | None = None
    AGENT_PUBSUB_TOPIC: str | None = None
    GCP_PROJECT_ID: str | None = None
    GCP_PUBSUB_TOPIC: str | None = None
    GCP_PUBSUB_TIMEOUT_SECONDS: float = 30.0
    # flat = TIM/Data canonical contract. legacy/envelope keeps the old framework wrapper.
    PUBSUB_PAYLOAD_MODE: Literal['flat','legacy','envelope','wrapped'] = 'flat'
    # Match the old Observer behavior: NOC.* goes to OTel Logs, not Pub/Sub.
    PUBSUB_EXCLUDE_NOC: bool = True

    # Automatic TIM/Data Pub/Sub sequence generation.
    # auto: Redis if configured; otherwise MongoDB if configured; otherwise memory fallback.
    # mongodb: atomic find_one_and_update/$inc, matching the legacy TIM Observer behavior.
    PUBSUB_SEQUENCE_ENABLED: bool = True
    PUBSUB_SEQUENCE_PROVIDER: Literal['auto','redis','mongodb','mongo','memory','none'] = 'auto'
    PUBSUB_SEQUENCE_REDIS_URL: str | None = None
    PUBSUB_SEQUENCE_MONGODB_URI: str | None = None
    PUBSUB_SEQUENCE_MONGODB_DATABASE: str | None = None
    PUBSUB_SEQUENCE_MONGODB_COLLECTION: str = 'observer_sequences'
    PUBSUB_SEQUENCE_TTL_SECONDS: int = 86400
    PUBSUB_SEQUENCE_MEMORY_FALLBACK: bool = True
    PUBSUB_SEQUENCE_KEY_PREFIX: str = 'observer:sequence'

    ANALYTICS_FAIL_SILENT: bool = True

    ENABLE_OCI_STREAMING: bool = False
    OCI_STREAM_ENDPOINT: str | None = None
    OCI_STREAM_OCID: str | None = None
    OCI_STREAM_PARTITION_KEY: str = 'agent-events'

    ENABLE_INPUT_GUARDRAILS: bool = True
    ENABLE_OUTPUT_GUARDRAILS: bool = True
    ENABLE_PARALLEL_GUARDRAILS: bool = True
    GUARDRAILS_FAIL_FAST: bool = True
    # Optional LLM inference points. Defaults keep the current deterministic behavior.
    ENABLE_JUDGES: bool = True
    ENABLE_SUPERVISOR: bool = True
    ENABLE_OUTPUT_SUPERVISOR: bool = True
    OUTPUT_SUPERVISOR_MAX_RETRIES: int = 3
    GUARDRAILS_CONFIG_PATH: str = './config/guardrails.yaml'
    JUDGES_CONFIG_PATH: str = './config/judges.yaml'
    PROMPT_POLICY_PATH: str = './config/prompt_policy.yaml'
    AGENTS_CONFIG_PATH: str = './config/agents.yaml'
    ROUTING_CONFIG_PATH: str = './config/routing.yaml'
    ENABLE_LLM_ROUTER: bool = False
    ROUTING_MODE: Literal['router','supervisor'] = 'router'

    # MCP / Tooling
    ENABLE_MCP_TOOLS: bool = True
    ENABLE_MCP_CACHE: bool = True
    MCP_CACHE_TTL_SECONDS: int = 300
    MCP_SERVERS_CONFIG_PATH: str = './config/mcp_servers.yaml'
    TOOLS_CONFIG_PATH: str = './config/tools.yaml'
    IDENTITY_CONFIG_PATH: str = './config/identity.yaml'
    MCP_PARAMETER_MAPPING_PATH: str = './config/mcp_parameter_mapping.yaml'
    MCP_TOOL_TIMEOUT_SECONDS: int = 30

    DEFAULT_CHANNEL: str = 'web'
    # Agent Framework channel input mode.
    # embedded = backend may use internal adapters to interpret simple/native payloads.
    # external = backend accepts only GatewayRequest payloads already normalized by an external Channel Gateway.
    FRAMEWORK_CHANNEL_INPUT_MODE: Literal['embedded','external'] = 'embedded'
    # Legacy alias kept for compatibility with older .env files. Prefer FRAMEWORK_CHANNEL_INPUT_MODE.
    CHANNEL_GATEWAY_MODE: str | None = None
    ENABLE_VOICE_ADAPTER: bool = True
    ENABLE_WHATSAPP_ADAPTER: bool = True
    ENABLE_TEXT_ADAPTER: bool = True


    # FIRST-ready runtime options
    SQLITE_DB_PATH: str = './data/agent_framework.db'
    ENABLE_SSE: bool = True
    SSE_KEEPALIVE_SECONDS: float = 15.0
    SSE_EVENT_REPLAY_LIMIT: int = 100
    ENABLE_MESSAGE_IDEMPOTENCY: bool = True
    ENABLE_LOCAL_CACHE: bool = True
    CACHE_TTL_SECONDS: int = 300
    CACHE_BACKEND_PROVIDER: Literal['memory','sqlite','autonomous','oracle'] = 'memory'
    SSE_STORE_PROVIDER: Literal['sqlite','autonomous','oracle'] | None = None

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
