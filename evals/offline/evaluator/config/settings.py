from __future__ import annotations

import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(ENV_PATH, override=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_PATH), extra="ignore", case_sensitive=False)

    adb_user: str = Field(default="", validation_alias="ADB_USER")
    adb_password: str = Field(default="", validation_alias="ADB_PASSWORD")
    adb_dsn: str = Field(default="", validation_alias="ADB_DSN")
    adb_wallet_location: str | None = Field(default=None, validation_alias="ADB_WALLET_LOCATION")
    adb_wallet_password: str | None = Field(default=None, validation_alias="ADB_WALLET_PASSWORD")
    adb_table_prefix: str = Field(default="AGENTFW", validation_alias="ADB_TABLE_PREFIX")

    enable_langfuse: bool = Field(default=False, validation_alias="ENABLE_LANGFUSE")
    langfuse_public_key: str | None = Field(default=None, validation_alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str | None = Field(default=None, validation_alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="http://localhost:3005", validation_alias="LANGFUSE_HOST")
    publish_langfuse_scores: bool = Field(default=False, validation_alias="PUBLISH_LANGFUSE_SCORES")

    # llm_provider: str = Field(default="mock", validation_alias="LLM_PROVIDER")
    # llm_profile: str = Field(default="judge", validation_alias="LLM_PROFILE")
    # llm_profiles_path: str = Field(default="configs/llm_profiles/llm_profiles.yaml", validation_alias="LLM_PROFILES_PATH")
    # oci_genai_endpoint: str | None = Field(default=None, validation_alias="OCI_GENAI_ENDPOINT")
    # oci_genai_model_id: str | None = Field(default=None, validation_alias="OCI_GENAI_MODEL_ID")
    # oci_genai_compartment_id: str | None = Field(default=None, validation_alias="OCI_GENAI_COMPARTMENT_ID")
    # oci_genai_auth_type: str = Field(default="api_key", validation_alias="OCI_GENAI_AUTH_TYPE")
    # oci_config_path: str | None = Field(default=None, validation_alias="OCI_CONFIG_PATH")
    # oci_config_profile: str = Field(default="DEFAULT", validation_alias="OCI_CONFIG_PROFILE")
    # llm_temperature: float = Field(default=0.0, validation_alias="LLM_TEMPERATURE")
    # llm_max_tokens: int = Field(default=900, validation_alias="LLM_MAX_TOKENS")

    # LLM / OCI GenAI OpenAI-compatible, mesmo padrão do Agent Framework
    llm_provider: str = Field(default="mock", validation_alias="LLM_PROVIDER")
    llm_profile: str = Field(default="judge", validation_alias="LLM_PROFILE")
    llm_profiles_path: str = Field(default="configs/llm_profiles/llm_profiles.yaml", validation_alias="LLM_PROFILES_PATH")

    oci_genai_base_url: str | None = Field(default=None, validation_alias="OCI_GENAI_BASE_URL")
    oci_genai_endpoint: str | None = Field(default=None, validation_alias="OCI_GENAI_ENDPOINT")  # compatibilidade
    oci_genai_model: str = Field(default="openai.gpt-4.1", validation_alias="OCI_GENAI_MODEL")
    oci_genai_model_id: str | None = Field(default=None, validation_alias="OCI_GENAI_MODEL_ID")  # compatibilidade
    oci_genai_api_key: str | None = Field(default=None, validation_alias="OCI_GENAI_API_KEY")
    oci_genai_project_ocid: str | None = Field(default=None, validation_alias="OCI_GENAI_PROJECT_OCID")

    llm_temperature: float = Field(default=0.0, validation_alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=900, validation_alias="LLM_MAX_TOKENS")
    llm_timeout_seconds: int = Field(default=120, validation_alias="LLM_TIMEOUT_SECONDS")

    agents_config_path: str = Field(default="configs/judge/agents.yaml", validation_alias="AGENTS_CONFIG_PATH")
    trace_prompt_path: str = Field(default="configs/judge/trace_metrics.yaml", validation_alias="TRACE_PROMPT_PATH")
    session_prompt_path: str = Field(default="configs/judge/session_metrics.yaml", validation_alias="SESSION_PROMPT_PATH")
    output_dir: str = Field(default="output", validation_alias="OUTPUT_DIR")
    batch_size: int = Field(default=50, validation_alias="BATCH_SIZE")
    max_attempts: int = Field(default=3, validation_alias="MAX_ATTEMPTS")
    enable_gcs_upload: bool = Field(default=False, validation_alias="ENABLE_GCS_UPLOAD")
    judge_gcs_bucket: str | None = Field(default=None, validation_alias="JUDGE_GCS_BUCKET")
    google_application_credentials: str | None = Field(default=None, validation_alias="GOOGLE_APPLICATION_CREDENTIALS")
    identity_config_path: str = "configs/identity.yaml"

    @property
    def project_root(self) -> Path:
        return ROOT_DIR

    def path(self, value: str | Path) -> Path:
        p = Path(value)
        return p if p.is_absolute() else ROOT_DIR / p

    @property
    def ADB_USER(self): return self.adb_user
    @property
    def ADB_PASSWORD(self): return self.adb_password
    @property
    def ADB_DSN(self): return self.adb_dsn
    @property
    def ADB_WALLET_LOCATION(self): return self.adb_wallet_location
    @property
    def ADB_WALLET_PASSWORD(self): return self.adb_wallet_password
    @property
    def ADB_TABLE_PREFIX(self): return (self.adb_table_prefix or "AGENTFW").upper().rstrip("_")

    @property
    def has_langfuse_credentials(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    @property
    def can_use_langfuse(self) -> bool:
        return bool(self.enable_langfuse and self.has_langfuse_credentials)

    @property
    def can_publish_langfuse_scores(self) -> bool:
        return bool(self.publish_langfuse_scores and self.can_use_langfuse)

    @property
    def OCI_GENAI_BASE_URL(self) -> str | None:
        return self.oci_genai_base_url or self.oci_genai_endpoint

    @property
    def OCI_GENAI_MODEL(self) -> str:
        return self.oci_genai_model_id or self.oci_genai_model

    @property
    def OCI_GENAI_API_KEY(self) -> str | None:
        return self.oci_genai_api_key

    @property
    def OCI_GENAI_PROJECT_OCID(self) -> str | None:
        return self.oci_genai_project_ocid

    @property
    def LLM_PROVIDER(self) -> str:
        return self.llm_provider

    @property
    def LLM_TEMPERATURE(self) -> float:
        return self.llm_temperature

    @property
    def LLM_MAX_TOKENS(self) -> int:
        return self.llm_max_tokens

    @property
    def LLM_TIMEOUT_SECONDS(self) -> int:
        return self.llm_timeout_seconds

    @property
    def LLM_PROFILES_PATH(self) -> str:
        return self.llm_profiles_path

settings = Settings()
if settings.ADB_WALLET_LOCATION:
    os.environ["TNS_ADMIN"] = settings.ADB_WALLET_LOCATION
