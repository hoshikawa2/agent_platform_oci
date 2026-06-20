"""Configuração feature-flag dos guardrails TIM.

Usa pydantic_settings.BaseSettings quando disponível (lê variáveis de
ambiente e .env automaticamente). Cai em dataclass com os.getenv quando
pydantic_settings não estiver instalado.

Convenção de nomes de env var: prefixo GUARDRAIL_ + nome do campo em
maiúsculas. Ex.: GUARDRAIL_PINJ_ENABLED, GUARDRAIL_TEST_MODE.

Exemplo de uso:
    from agente_contas_tim.guardrails.config import GuardRailConfig
    cfg = GuardRailConfig()
    if cfg.oos_enabled:
        ...
"""
from __future__ import annotations

import os
from decimal import Decimal

try:
    from pydantic_settings import BaseSettings
    from pydantic import Field

    class GuardRailConfig(BaseSettings):
        """Feature flags e limites dos guardrails TIM.

        Todos os campos têm defaults conservadores (False / zero) para que
        o pipeline mantenha o comportamento atual enquanto rails novos são
        validados em staging.

        Grupos:
            Input rails:
                pinj_enabled      — Prompt Injection / Jailbreak.
                input_size_enabled — Tamanho máximo de input.
                msk_enabled       — Mascaramento de PII no input.
                tox_enabled       — Toxicidade no input (desativado por latência).
                dlex_in_enabled   — Data Leakage no input.
            Output rails:
                oos_enabled       — Out-of-Scope.
                aoferta_enabled   — Ausência de Oferta Proativa.
                anatel_enabled    — Compliance Anatel (protocolo obrigatório).
                revprec_enabled   — Verbalizacao Prematura.
                ragsec_enabled    — RAG Security / Context Poisoning.
                dlex_out_enabled  — Data Leakage no output.
            Test:
                test_mode         — Ativa bypass controlado p/ testes de fumaça.
                                    Substitui o bypass hardcoded ###teste[1,2,3,4]###
                                    que existia em out_of_scope.py.
            Específicos:
                alcada_ajuste_enabled — Habilita validação de alçada em ajustes.
                alcada_ajuste_max_value — Valor máximo (R$) permitido sem escalonamento.
        """

        model_config = {"env_prefix": "GUARDRAIL_", "env_file": ".env", "extra": "ignore"}

        # --- Input rails ---
        pinj_enabled: bool = Field(default=True)
        input_size_enabled: bool = Field(default=True)
        msk_enabled: bool = Field(default=True)
        tox_enabled: bool = Field(default=False)
        dlex_in_enabled: bool = Field(default=False)

        # --- Output rails ---
        oos_enabled: bool = Field(default=True)
        aoferta_enabled: bool = Field(default=True)
        anatel_enabled: bool = Field(default=True)
        revprec_enabled: bool = Field(default=False)
        ragsec_enabled: bool = Field(default=False)
        dlex_out_enabled: bool = Field(default=False)

        # --- Test mode ---
        test_mode: bool = Field(default=False)

        # --- Alçada de ajuste ---
        alcada_ajuste_enabled: bool = Field(default=False)
        alcada_ajuste_max_value: Decimal = Field(default=Decimal("0"))

except ImportError:
    # Fallback para dataclass quando pydantic_settings não está disponível.
    import dataclasses

    def _bool_env(name: str, default: bool) -> bool:
        val = os.getenv(f"GUARDRAIL_{name.upper()}", str(default)).lower()
        return val in ("1", "true", "yes", "on")

    def _decimal_env(name: str, default: Decimal) -> Decimal:
        val = os.getenv(f"GUARDRAIL_{name.upper()}")
        if val is None:
            return default
        try:
            return Decimal(val)
        except Exception:
            return default

    @dataclasses.dataclass
    class GuardRailConfig:  # type: ignore[no-redef]
        """Feature flags e limites dos guardrails TIM (fallback sem pydantic_settings)."""

        # Input rails
        pinj_enabled: bool = dataclasses.field(default_factory=lambda: _bool_env("pinj_enabled", True))
        input_size_enabled: bool = dataclasses.field(default_factory=lambda: _bool_env("input_size_enabled", True))
        msk_enabled: bool = dataclasses.field(default_factory=lambda: _bool_env("msk_enabled", True))
        tox_enabled: bool = dataclasses.field(default_factory=lambda: _bool_env("tox_enabled", False))
        dlex_in_enabled: bool = dataclasses.field(default_factory=lambda: _bool_env("dlex_in_enabled", False))

        # Output rails
        oos_enabled: bool = dataclasses.field(default_factory=lambda: _bool_env("oos_enabled", True))
        aoferta_enabled: bool = dataclasses.field(default_factory=lambda: _bool_env("aoferta_enabled", True))
        anatel_enabled: bool = dataclasses.field(default_factory=lambda: _bool_env("anatel_enabled", True))
        revprec_enabled: bool = dataclasses.field(default_factory=lambda: _bool_env("revprec_enabled", False))
        ragsec_enabled: bool = dataclasses.field(default_factory=lambda: _bool_env("ragsec_enabled", False))
        dlex_out_enabled: bool = dataclasses.field(default_factory=lambda: _bool_env("dlex_out_enabled", False))

        # Test mode
        test_mode: bool = dataclasses.field(default_factory=lambda: _bool_env("test_mode", False))

        # Alçada de ajuste
        alcada_ajuste_enabled: bool = dataclasses.field(default_factory=lambda: _bool_env("alcada_ajuste_enabled", False))
        alcada_ajuste_max_value: Decimal = dataclasses.field(default_factory=lambda: _decimal_env("alcada_ajuste_max_value", Decimal("0")))


__all__ = ["GuardRailConfig"]
