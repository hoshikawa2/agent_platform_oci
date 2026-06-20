from __future__ import annotations
from dataclasses import dataclass, field
import yaml
from pathlib import Path
from evaluator.config.settings import settings

@dataclass
class AgentConfig:
    agent_id: str
    enabled: bool = True
    days_back: int = 1
    percentage: float = 1.0
    langfuse_agent_aliases: list[str] = field(default_factory=list)
    gcs_prefix: str = ""

    @property
    def aliases(self) -> set[str]:
        return {self.agent_id, *self.langfuse_agent_aliases}


def load_agents(path: str | None = None) -> list[AgentConfig]:
    p = settings.path(path or settings.agents_config_path)
    data = yaml.safe_load(p.read_text()) or {}
    agents = []
    for item in data.get("agents", []):
        cfg = AgentConfig(
            agent_id=item["agent_id"],
            enabled=bool(item.get("enabled", True)),
            days_back=int(item.get("days_back", item.get("daysBack", 1))),
            percentage=float(item.get("percentage", 1.0)),
            langfuse_agent_aliases=list(item.get("langfuse_agent_aliases", [])),
            gcs_prefix=str(item.get("gcs_prefix", "")),
        )
        if cfg.enabled:
            agents.append(cfg)
    return agents
