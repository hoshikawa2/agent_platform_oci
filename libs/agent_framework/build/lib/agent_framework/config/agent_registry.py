from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


@dataclass
class AgentProfile:
    agent_id: str
    name: str = ""
    description: str = ""
    prompt_policy_path: str | None = None
    routing_config_path: str | None = None
    guardrails_config_path: str | None = None
    judges_config_path: str | None = None
    mcp_servers_config_path: str | None = None
    tools_config_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentProfileRegistry:
    """Carrega perfis de agentes/templates a partir de YAML.

    O objetivo é permitir múltiplos agent_template no mesmo backend sem misturar
    memória, checkpoints, prompts, guardrails ou judges.
    """

    def __init__(self, settings):
        self.settings = settings
        self.base_dir = Path.cwd()
        self.profiles: dict[str, AgentProfile] = {}
        self.default_agent_id = "default_agent"
        self._load()

    def _resolve(self, value: str | None) -> str | None:
        if not value:
            return None
        path = Path(value)
        return str(path if path.is_absolute() else (self.base_dir / path).resolve())

    def _load(self) -> None:
        config_path = Path(getattr(self.settings, "AGENTS_CONFIG_PATH", "./config/agents.yaml"))
        if not config_path.is_absolute():
            config_path = self.base_dir / config_path
        if not config_path.exists() or yaml is None:
            self.profiles[self.default_agent_id] = AgentProfile(
                agent_id=self.default_agent_id,
                name="Default Agent",
                prompt_policy_path=self._resolve(getattr(self.settings, "PROMPT_POLICY_PATH", None)),
                routing_config_path=self._resolve(getattr(self.settings, "ROUTING_CONFIG_PATH", None)),
                guardrails_config_path=self._resolve(getattr(self.settings, "GUARDRAILS_CONFIG_PATH", None)),
                judges_config_path=self._resolve(getattr(self.settings, "JUDGES_CONFIG_PATH", None)),
                mcp_servers_config_path=self._resolve(getattr(self.settings, "MCP_SERVERS_CONFIG_PATH", None)),
                tools_config_path=self._resolve(getattr(self.settings, "TOOLS_CONFIG_PATH", None)),
            )
            return

        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        self.default_agent_id = raw.get("default_agent_id") or self.default_agent_id
        for item in raw.get("agents", []):
            agent_id = str(item.get("agent_id") or item.get("id") or "").strip()
            if not agent_id:
                continue
            self.profiles[agent_id] = AgentProfile(
                agent_id=agent_id,
                name=item.get("name", agent_id),
                description=item.get("description", ""),
                prompt_policy_path=self._resolve(item.get("prompt_policy_path") or getattr(self.settings, "PROMPT_POLICY_PATH", None)),
                routing_config_path=self._resolve(item.get("routing_config_path") or getattr(self.settings, "ROUTING_CONFIG_PATH", None)),
                guardrails_config_path=self._resolve(item.get("guardrails_config_path") or getattr(self.settings, "GUARDRAILS_CONFIG_PATH", None)),
                judges_config_path=self._resolve(item.get("judges_config_path") or getattr(self.settings, "JUDGES_CONFIG_PATH", None)),
                mcp_servers_config_path=self._resolve(item.get("mcp_servers_config_path") or getattr(self.settings, "MCP_SERVERS_CONFIG_PATH", None)),
                tools_config_path=self._resolve(item.get("tools_config_path") or getattr(self.settings, "TOOLS_CONFIG_PATH", None)),
                metadata=item.get("metadata") or {},
            )
        if self.default_agent_id not in self.profiles and self.profiles:
            self.default_agent_id = next(iter(self.profiles))

    def get(self, agent_id: str | None = None) -> AgentProfile:
        key = agent_id or self.default_agent_id
        return self.profiles.get(key) or self.profiles[self.default_agent_id]

    def list_profiles(self) -> list[AgentProfile]:
        return list(self.profiles.values())
