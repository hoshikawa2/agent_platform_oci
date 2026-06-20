from __future__ import annotations

import os
from typing import Any

from .base import RailDecision
from .config_loader import load_guardrails_config
from .parallel_executor import ParallelRailExecutor, TERMINAL_ACTIONS
from .rail_action import RailAction
from .rails import (
    ComplianceRail,
    DataLeakageInputRail,
    DataLeakageOutputRail,
    GroundednessRail,
    HallucinationRiskRail,
    JailbreakRail,
    LoopRail,
    MessageSizeRail,
    OutOfScopeRail,
    OutputPiiMaskRail,
    OutputToxicitySanitizationRail,
    PiiMaskRail,
    PrematureActionRail,
    ProactiveOfferRail,
    PromptInjectionRail,
    RagSecurityRail,
    RetrievalRelevanceRail,
    ToolValidationRail,
    ToxicityRail,
)


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


class GuardrailPipeline:
    """Pipeline default de rails com suporte a execução paralela fail-fast.

    Por padrão o pipeline agora executa rails de input/output em paralelo.
    O primeiro rail que retornar ação terminal (block/retry/handover) encerra a
    rodada e cancela os demais. Sanitizações são aplicadas em ordem estável.

    Para compatibilidade, o retorno público continua sendo:
        (texto_final, list[RailDecision legado])

    A otimização pode ser desligada por configuração/env:
        ENABLE_PARALLEL_GUARDRAILS=false
    """

    def __init__(
        self,
        input_rails=None,
        output_rails=None,
        retrieval_rails=None,
        tool_rails=None,
        *,
        observer: Any | None = None,
        enable_parallel: bool | None = None,
        fail_fast: bool | None = None,
        llm: Any | None = None,
        enable_llm_guardrail: bool | None = None,
        llm_fail_closed: bool = False,
        config_path: str | None = None,
    ):
        self.guardrails_config = load_guardrails_config(config_path)
        self.config_loaded = bool(self.guardrails_config.loaded)

        if input_rails is None:
            if self.config_loaded:
                self.input_rails = list(self.guardrails_config.input_rails or [])
            else:
                self.input_rails = [
                    MessageSizeRail(),
                    PiiMaskRail(),
                    ToxicityRail(),
                    PromptInjectionRail(),
                    LoopRail(),
                    DataLeakageInputRail(),
                ]
                # Compatibilidade antiga apenas quando não há guardrails.yaml.
                if _truthy(os.getenv("GUARDRAIL_OOS_ENABLED"), False):
                    self.input_rails.append(OutOfScopeRail())
        else:
            self.input_rails = input_rails

        if output_rails is None:
            if self.config_loaded:
                self.output_rails = list(self.guardrails_config.output_rails or [])
            else:
                self.output_rails = [
                    OutputPiiMaskRail(),
                    OutputToxicitySanitizationRail(),
                    ComplianceRail(),
                    ProactiveOfferRail(),
                    PrematureActionRail(),
                    DataLeakageOutputRail(),
                    GroundednessRail(),
                    HallucinationRiskRail(),
                ]
        else:
            self.output_rails = output_rails

        if retrieval_rails is None:
            self.retrieval_rails = list(self.guardrails_config.retrieval_rails or []) if self.config_loaded else [RetrievalRelevanceRail(), RagSecurityRail(), PiiMaskRail()]
        else:
            self.retrieval_rails = retrieval_rails

        if tool_rails is None:
            self.tool_rails = list(self.guardrails_config.tool_rails or []) if self.config_loaded else [ToolValidationRail()]
        else:
            self.tool_rails = tool_rails
        self.llm = llm
        # The generic legacy LLM guardrail was removed from the default pipeline.
        # Calibrated rails such as PINJ, TOX, OOS, REVPREC, AOFERTA, DLEX_* and
        # RAGSEC decide individually when they need the LLM and which profile
        # (guardrail/grl) they must use. Keeping the old catch-all rail produced
        # duplicate/ambiguous telemetry such as LEGACY_OUTPUT_GUARDRAIL.
        self.enable_llm_guardrail = False
        self.observer = observer
        self.enable_parallel = _truthy(os.getenv("ENABLE_PARALLEL_GUARDRAILS"), True) if enable_parallel is None else enable_parallel
        self.fail_fast = _truthy(os.getenv("GUARDRAILS_FAIL_FAST"), True) if fail_fast is None else fail_fast
        self.executor = ParallelRailExecutor(fail_fast=self.fail_fast, observer=observer)

    async def _run_sequential(self, text: str, context: dict[str, Any], rails: list) -> tuple[str, list[RailDecision]]:
        current = text
        decisions: list[RailDecision] = []
        for rail in rails:
            decision = await rail.evaluate(current, context)
            decisions.append(decision)
            if decision.sanitized_text is not None:
                current = decision.sanitized_text
            if not decision.allowed:
                return current, decisions
        return current, decisions

    async def _run_parallel(self, text: str, context: dict[str, Any], rails: list, *, stage: str) -> tuple[str, list[RailDecision]]:
        execution = await self.executor.run(text, context, rails, fail_fast=self.fail_fast, stage=stage)
        decisions: list[RailDecision] = []

        for result in execution.results:
            legacy_model = result.metadata.get("legacy_decision_model") if isinstance(result.metadata, dict) else None
            if isinstance(legacy_model, dict):
                decisions.append(RailDecision(**legacy_model))
            else:
                allowed = result.action not in TERMINAL_ACTIONS
                decisions.append(
                    RailDecision(
                        code=result.code,
                        allowed=allowed,
                        reason=result.reason,
                        sanitized_text=result.sanitized_text,
                        metadata={
                            **dict(result.metadata or {}),
                            "action": result.action.value,
                            "guidance": result.guidance,
                            "parallel_executor": True,
                        },
                    )
                )

        if execution.cancelled_codes:
            decisions.append(
                RailDecision(
                    code="PARALLEL_CANCELLED",
                    allowed=True,
                    metadata={"cancelled_codes": execution.cancelled_codes, "stage": stage},
                )
            )
        return execution.text, decisions

    async def _run(self, text: str, context: dict[str, Any], rails: list, *, stage: str = "guardrail") -> tuple[str, list[RailDecision]]:
        run_context = dict(context or {})
        # Disponibiliza o LLM do framework para rails calibrados sem criar cliente paralelo.
        if self.llm is not None:
            run_context.setdefault("llm", self.llm)
            run_context.setdefault("guardrail_llm", self.llm)
        run_context.setdefault("__guardrails_config_loaded", self.config_loaded)
        if self.config_loaded:
            run_context.setdefault("__guardrails_config_path", self.guardrails_config.path)
            run_context.setdefault("__guardrails_yaml_controlled", True)
        if not self.enable_parallel:
            return await self._run_sequential(text, run_context, rails)
        return await self._run_parallel(text, run_context, rails, stage=stage)

    async def run_input(self, text, context):
        return await self._run(text, context or {}, self.input_rails, stage="input")

    async def run_output(self, text, context):
        current, decisions = await self._run(text, context or {}, self.output_rails, stage="output")
        if any((not decision.allowed and decision.code == "REVPREC") for decision in decisions):
            return (
                "Não posso confirmar essa ação sem validação operacional. Posso explicar o próximo passo.",
                decisions,
            )
        return current, decisions

    async def run_retrieval(self, chunk_text: str, context: dict[str, Any] | None = None):
        return await self._run(chunk_text, context or {}, self.retrieval_rails, stage="retrieval")

    async def run_tool(self, tool_name: str, tool_args: dict[str, Any], context: dict[str, Any] | None = None):
        ctx = dict(context or {})
        ctx.setdefault("tool_name", tool_name)
        ctx.setdefault("tool_args", tool_args or {})
        return await self._run(tool_name, ctx, self.tool_rails, stage="tool")
