from __future__ import annotations

from typing import Any

from .pipeline import GuardrailPipeline
from .config_loader import load_guardrails_config
from .rails import (
    ComplianceRail,
    DataLeakageInputRail,
    DataLeakageOutputRail,
    MessageSizeRail,
    OutputPiiMaskRail,
    OutputToxicitySanitizationRail,
    PiiMaskRail,
    PrematureActionRail,
    ProactiveOfferRail,
    PromptInjectionRail,
    ToxicityRail,
)


class CustomRails:
    """Ponto de extensão para agentes TIM.

    Subclasses implementam configure() e registram rails específicos com add().
    O bundle mínimo é carregado por padrão para manter piso de segurança.
    """

    def __init__(self, *, skip_default_bundle: bool = False, llm: Any | None = None, observer: Any | None = None):
        self.llm = llm
        self.observer = observer
        self.input_rails: list[Any] = []
        self.output_rails: list[Any] = []
        if not skip_default_bundle:
            self._load_default_bundle()
        self.configure()

    def _load_default_bundle(self) -> None:
        cfg = load_guardrails_config()
        if cfg.loaded:
            self.input_rails.extend(list(cfg.input_rails or []))
            self.output_rails.extend(list(cfg.output_rails or []))
            return
        self.input_rails.extend([MessageSizeRail(), PiiMaskRail(), ToxicityRail(), PromptInjectionRail(), DataLeakageInputRail()])
        self.output_rails.extend([OutputPiiMaskRail(), OutputToxicitySanitizationRail(), ComplianceRail(), ProactiveOfferRail(), PrematureActionRail(), DataLeakageOutputRail()])

    def configure(self) -> None:
        """Override em subclasses."""

    def add(self, rail: Any, *, stage: str | None = None) -> None:
        target_stage = stage or getattr(rail, "stage", "input")
        if target_stage == "output":
            self.output_rails.append(rail)
        else:
            self.input_rails.append(rail)

    def as_pipeline(self) -> GuardrailPipeline:
        return GuardrailPipeline(input_rails=self.input_rails, output_rails=self.output_rails, llm=self.llm, observer=self.observer)

    async def apply_input(self, user_message: str, **ctx: Any):
        return await self.as_pipeline().run_input(user_message, ctx)

    async def apply_output(self, candidate_response: str, **ctx: Any):
        return await self.as_pipeline().run_output(candidate_response, ctx)
