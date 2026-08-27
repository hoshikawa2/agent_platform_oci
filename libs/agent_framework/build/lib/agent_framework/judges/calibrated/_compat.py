"""Compatibilidade com primitivos do agent_framework.guardrails_old.

A lib (agent_framework 2.1.1) tem dois imports eager problematicos:

1. agent_framework/__init__.py instancia google.cloud.pubsub_v1.PublisherClient
   no carregamento, exigindo GOOGLE_APPLICATION_CREDENTIALS no ambiente.
2. agent_framework/guardrails/nemo/__init__.py importa .factory que importa
   nemoguardrails, mesmo para usos do Padrao 1 (rails individuais) que o
   guia da lib documenta como nao requerendo nemoguardrails.

Este modulo tenta importar RailResult e span direto da lib legacy
(`guardrails_old`) para manter compatibilidade com os rails NeMo antigos.
Quando isso falha por qualquer motivo, cai num clone local com
exatamente os mesmos campos/assinaturas — instancias sao estruturalmente
indistinguiveis das da lib, intercambiaveis em qualquer downstream
(serializers, dashboards, executar_atendimento etc).
"""
from __future__ import annotations

try:
    from agent_framework.guardrails_old.nemo.models import RailResult  # noqa: F401
    from agent_framework.guardrails_old.nemo.tracing import span  # noqa: F401
except Exception:
    from contextlib import contextmanager
    from dataclasses import dataclass
    from typing import Any

    @dataclass
    class RailResult:
        allowed: bool
        reason: str
        sanitized_text: str | None = None
        code: str | None = None
        mechanism: str | None = None
        data: dict[str, Any] | None = None

    @contextmanager
    def span(name: str, **kwargs):
        yield


__all__ = ["RailResult", "span"]
