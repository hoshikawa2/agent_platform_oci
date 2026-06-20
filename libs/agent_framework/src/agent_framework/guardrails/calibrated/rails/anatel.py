"""AnatelRail — compliance de protocolo obrigatório ANATEL.

Rail determinístico (sem LLM): verifica se a resposta do agente contém
o número de protocolo obrigatório quando o fluxo é do tipo "ajuste" ou
quando `requer_protocolo=True` está sinalizado nos metadados do agente.

Quando o protocolo está ausente, aplica fallback determinístico:
vocaliza os números crus de `expected_protocols` e os anexa ao texto.

Lógica replicada de:
    agent/infra/langchain/agent/core.py
        _apply_compliance_anatel_fallback_to_text()
        _apply_compliance_protocol_fallback()

O original no core.py NÃO foi alterado — este módulo é a nova implementação
desacoplada para uso via Protocol Rail.

Exemplo de uso:
    from agente_contas_tim.guardrails.rails.anatel import AnatelRail
    from agente_contas_tim.guardrails.contracts import GuardRailContext

    rail = AnatelRail()
    ctx = GuardRailContext(
        session_id="abc",
        user_text="Seu ajuste foi processado.",
        agent_metadata={
            "tipo_fluxo": "ajuste",
            "expected_protocols": ["PRT-123456"],
            "requer_protocolo": True,
        },
    )
    decision = rail.evaluate(ctx)
    # decision.allowed == False  (protocolo não vocalizado no texto)
    # decision.sanitized_text   (texto com protocolo anexado)
"""
from __future__ import annotations

import logging
import re

from ..contracts import GuardRailContext, RailDecision

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Padrão regex idêntico ao de llm_rails.py (_PROTOCOL_PATTERN)
# ---------------------------------------------------------------------------

_DIGIT_WORDS_RE = r"(?:zero|um|dois|tr[êe]s|quatro|cinco|seis|sete|oito|nove)"
_SPOKEN_TOKEN_RE = rf"(?:{_DIGIT_WORDS_RE}|[a-z])"
_SPOKEN_PROTOCOL_RE = rf"(?:{_SPOKEN_TOKEN_RE}\s+){{5,}}{_SPOKEN_TOKEN_RE}\b"

_PROTOCOL_PATTERN = re.compile(
    r"(?i)\bprotocolo\b"
    r"[\s\S]{0,40}?"
    r"(?:"
        r"\d{6,}"
        r"|"
        r"PRT-[A-Z0-9]{6,}"
        r"|"
        rf"{_SPOKEN_PROTOCOL_RE}"
    r")"
)

# Mapeamento de dígito para palavra PT-BR
_DIGIT_TO_WORD: dict[str, str] = {
    "0": "zero", "1": "um", "2": "dois", "3": "três",
    "4": "quatro", "5": "cinco", "6": "seis", "7": "sete",
    "8": "oito", "9": "nove",
}

# Mapeamento de letra para nome da letra PT-BR (vogais e consoantes comuns)
_LETTER_TO_WORD: dict[str, str] = {
    "a": "a", "b": "bê", "c": "cê", "d": "dê", "e": "e",
    "f": "efe", "g": "gê", "h": "agá", "i": "i", "j": "jota",
    "k": "ká", "l": "ele", "m": "eme", "n": "ene", "o": "o",
    "p": "pê", "q": "quê", "r": "erre", "s": "esse", "t": "tê",
    "u": "u", "v": "vê", "w": "dáblio", "x": "xis", "y": "ípsilon",
    "z": "zê",
}


def _vocalize(value: str) -> str:
    """Converte string de protocolo (dígitos e letras) em palavras PT-BR.

    Replica o comportamento de text_utils.vocalize_digits, mas opera sobre
    a string completa de um protocolo (ex.: "PRT-ABC123" -> vocaliza cada
    caractere alfanumérico separado por espaço).

    Importa de text_utils quando disponível; caso contrário usa a lógica
    local acima.
    """
    try:
        from agente_contas_tim.text_utils import vocalize_digits  # noqa: PLC0415
        return vocalize_digits(value)
    except Exception:
        pass

    # Fallback local: vocaliza caractere a caractere
    tokens: list[str] = []
    for ch in value.lower():
        if ch in _DIGIT_TO_WORD:
            tokens.append(_DIGIT_TO_WORD[ch])
        elif ch in _LETTER_TO_WORD:
            tokens.append(_LETTER_TO_WORD[ch])
        elif ch in ("-", "_", " "):
            continue  # separadores ignorados
    return " ".join(tokens)


class AnatelRail:
    """Rail determinístico de compliance ANATEL.

    Implementa o Protocol Rail de contracts.py.

    Avalia se a resposta do agente contém o número de protocolo quando
    o fluxo exige (tipo_fluxo='ajuste' ou requer_protocolo=True).

    Quando o protocolo está faltando:
    - allowed=False
    - sanitized_text contém o texto original + sufixo(s) de protocolo vocalizado(s)

    Quando o protocolo não é exigido ou já está presente:
    - allowed=True
    - sanitized_text == user_text original (sem alteração)
    """

    @property
    def code(self) -> str:
        return "CMP"

    @property
    def fallback_text(self) -> str | None:
        """ANATEL é rail de transformação (sanitize-and-pass-through), não hard-blocking."""
        return None

    @property
    def regen_flag(self) -> str | None:
        return None

    @property
    def is_soft_alert(self) -> bool:
        return False

    def evaluate(self, context: GuardRailContext) -> RailDecision:
        """Avalia o texto do agente quanto ao protocolo ANATEL obrigatório.

        Args:
            context: GuardRailContext com:
                - user_text: resposta do agente a auditar.
                - agent_metadata: deve conter 'tipo_fluxo', 'requer_protocolo'
                  e 'expected_protocols'.

        Returns:
            RailDecision com allowed=True quando o protocolo está presente
            ou não é exigido; allowed=False com sanitized_text corrigido
            quando o protocolo está faltando.
        """
        meta = context.agent_metadata or {}
        text = context.user_text

        requer = (
            meta.get("tipo_fluxo") == "ajuste"
            or meta.get("requer_protocolo") is True
        )

        if not requer:
            return RailDecision(
                allowed=True,
                code=self.code,
                reason="Compliance Anatel não aplicável para este fluxo",
                sanitized_text=text,
            )

        expected = list(meta.get("expected_protocols") or [])
        has_protocol = bool(_PROTOCOL_PATTERN.search(text))

        if has_protocol:
            return RailDecision(
                allowed=True,
                code=self.code,
                reason="Resposta contém protocolo obrigatório",
                sanitized_text=text,
            )

        # Protocolo ausente: aplica fallback determinístico
        patched, missing_spoken = self._apply_protocol_fallback(text, expected)

        if patched == text:
            # Regex falhou mas _apply encontrou os protocolos já no texto
            # (false positive do padrão) — deixa passar
            logger.debug(
                "anatel_rail.regex_false_positive expected=%s text=%r",
                expected,
                text[:200],
            )
            return RailDecision(
                allowed=True,
                code=self.code,
                reason="Protocolo encontrado em formato não-padrão — falso positivo do regex",
                sanitized_text=text,
            )

        logger.warning(
            "anatel_rail.protocol_missing missing=%s original=%r",
            missing_spoken,
            text[:200],
        )
        return RailDecision(
            allowed=False,
            code=self.code,
            reason=f"Resposta de ajuste sem número de protocolo — {len(missing_spoken)} protocolo(s) anexado(s)",
            sanitized_text=patched,
        )

    def _apply_protocol_fallback(
        self, text: str, expected_protocols: list[str]
    ) -> tuple[str, list[str]]:
        """Vocaliza protocolos faltantes e os anexa ao texto.

        Para cada protocolo cru em expected_protocols, vocaliza e verifica
        se já está no texto (em qualquer formato razoável). Se faltar, anexa
        ao final.

        Returns:
            Tupla (texto_patched, lista_de_protocolos_vocalizados_inseridos).
            Quando nenhum protocolo está faltando, retorna (text_original, []).
        """
        missing_spoken: list[str] = []
        for raw in expected_protocols:
            spoken = _vocalize(raw)
            if spoken and spoken in text:
                continue
            if raw and raw in text:
                continue
            if spoken:
                missing_spoken.append(spoken)

        if not missing_spoken:
            return text, []

        suffix = " ".join(
            f"Seu número de protocolo é {s}." for s in missing_spoken
        )
        patched = f"{text.rstrip()} {suffix}".strip()
        return patched, missing_spoken


__all__ = ["AnatelRail"]
