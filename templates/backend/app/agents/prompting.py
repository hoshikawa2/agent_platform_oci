from __future__ import annotations


def apply_agent_profile_prompt(state: dict, default_prompt: str) -> str:
    """Adiciona o prefixo de prompt configurado para o agent_template selecionado.

    Cada agent_id pode definir metadata.system_prefix em config/agents.yaml. Isso
    mantém prompts isolados sem duplicar o código dos agentes especializados.
    """
    profile = state.get("agent_profile") or (state.get("context") or {}).get("agent_profile") or {}
    metadata = profile.get("metadata") or {}
    prefix = (metadata.get("system_prefix") or "").strip()
    if not prefix:
        return default_prompt
    return f"{prefix}\n\n{default_prompt}"
