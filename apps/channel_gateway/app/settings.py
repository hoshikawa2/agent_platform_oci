from __future__ import annotations

from typing import Literal
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv(override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    APP_NAME: str = 'external-channel-gateway'
    LOG_LEVEL: str = 'INFO'
    API_HOST: str = '0.0.0.0'
    API_PORT: int = 7000
    CORS_ORIGINS: str = 'http://localhost:5173,http://127.0.0.1:5173'

    # adapter = receive native/simple channel payloads and translate them to GatewayRequest.
    # proxy   = receive only GatewayRequest and forward it after validation.
    CHANNEL_GATEWAY_RUNTIME_MODE: Literal['adapter','proxy'] = 'adapter'
    # Legacy alias accepted only for compatibility. Prefer CHANNEL_GATEWAY_RUNTIME_MODE.
    CHANNEL_GATEWAY_MODE: str | None = None

    AGENT_FRAMEWORK_BASE_URL: str = 'http://localhost:8000'
    AGENT_FRAMEWORK_GATEWAY_PATH: str = '/gateway/message'
    DEFAULT_TENANT_ID: str = 'default'
    DEFAULT_AGENT_ID: str = 'telecom_contas'
    REQUEST_TIMEOUT_SECONDS: float = 120.0

    INTERNAL_GATEWAY_TOKEN: str | None = None

    @property
    def runtime_mode(self) -> str:
        legacy = (self.CHANNEL_GATEWAY_MODE or '').strip().lower()
        if legacy in {'adapter', 'proxy'}:
            return legacy
        # Legacy mapping for old deployments: embedded meant adapters on.
        if legacy == 'embedded':
            return 'adapter'
        if legacy == 'external':
            return 'proxy'
        return self.CHANNEL_GATEWAY_RUNTIME_MODE


settings = Settings()
