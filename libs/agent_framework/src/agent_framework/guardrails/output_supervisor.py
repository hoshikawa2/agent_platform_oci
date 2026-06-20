from __future__ import annotations

import logging
from typing import Any, Iterable

from .base import RailDecision as LegacyRailDecision
from .rail_action import RailAction
from .rail_decision import RailDecisionV2
from .rail_result import RailResult
from .parallel_executor import ParallelRailExecutor
from .llm_rails import LLMOutputGRLRail
from .config_loader import load_guardrails_config

logger = logging.getLogger("agent_framework.guardrails.output_supervisor")


_SEVERITY = {
    RailAction.HANDOVER: 4,
    RailAction.BLOCK: 3,
    RailAction.RETRY: 2,
    RailAction.SANITIZE: 1,
    RailAction.ALLOW: 0,
    RailAction.OBSERVE: 0,
}


class OutputSupervisor:
    """Supervisor de qualidade de saída, alinhado à Fundação TIM.

    Não substitui o supervisor de roteamento. Este componente roda depois do
    agente gerar a resposta candidata e decide se libera, sanitiza, pede retry,
    bloqueia ou solicita handover.
    """

    def __init__(
        self,
        rails: Iterable[Any] | None = None,
        *,
        fallback_message: str | None = None,
        max_retries: int = 3,
        observer: Any | None = None,
        fail_closed_action: RailAction = RailAction.BLOCK,
        enable_parallel: bool = True,
        fail_fast: bool = True,
        llm: Any | None = None,
        enable_llm_grl: bool = False,
        llm_fail_closed: bool = False,
        config_path: str | None = None,
    ):
        self.guardrails_config = load_guardrails_config(config_path)
        self.config_loaded = bool(self.guardrails_config.loaded)

        # guardrails.yaml is the source of truth when present. The OutputSupervisor
        # used to start with an empty rail list unless the caller manually passed
        # rails, while GuardrailPipeline correctly loaded the YAML. This made input
        # rails obey guardrails.yaml but output flows that used OutputSupervisor
        # skip REVPREC/AOFERTA/CMP/etc. Load output rails here as well.
        if rails is None:
            self.rails = list(self.guardrails_config.output_rails or []) if self.config_loaded else []
        else:
            self.rails = list(rails or [])

        # Do not append the legacy catch-all LLM output rail when guardrails.yaml
        # exists. In YAML-controlled mode, only rails explicitly enabled in the
        # output section may run or emit telemetry.
        if (not self.config_loaded) and enable_llm_grl and llm is not None:
            self.rails.append(LLMOutputGRLRail(llm, fail_closed=llm_fail_closed))
        self.llm = llm
        self.fallback_message = fallback_message or "Não consegui validar essa resposta com segurança. Posso reformular a resposta."
        self.max_retries = max_retries
        self.observer = observer
        self.fail_closed_action = fail_closed_action
        self.enable_parallel = enable_parallel
        self.fail_fast = fail_fast
        self.executor = ParallelRailExecutor(fail_fast=fail_fast, observer=observer, stage="output")

    async def evaluate(self, candidate: str, context: dict[str, Any] | None = None) -> RailDecisionV2:
        ctx = dict(context or {})
        if self.llm is not None:
            ctx.setdefault("llm", self.llm)
            ctx.setdefault("guardrail_llm", self.llm)
        if self.config_loaded:
            ctx.setdefault("__guardrails_config_loaded", True)
            ctx.setdefault("__guardrails_config_path", self.guardrails_config.path)
            ctx.setdefault("__guardrails_yaml_controlled", True)
        visible_rails = [getattr(r, "code", r.__class__.__name__) for r in self.rails if not self._is_suppressed_legacy_code(getattr(r, "code", r.__class__.__name__))]
        await self._emit("GRL.001", {"stage": "output", "rails": visible_rails}, ctx)

        if not self.rails:
            result = RailResult(code="NO_RAILS", action=RailAction.ALLOW, reason="Nenhum rail configurado")
            decision = RailDecisionV2(action=RailAction.ALLOW, results=[result], candidate=candidate)
            await self._emit_final(decision, ctx)
            return decision

        if self.enable_parallel:
            execution = await self.executor.run(candidate, ctx, self.rails, fail_fast=self.fail_fast, stage="output_supervisor")
            results = list(execution.results)
            if execution.cancelled_codes:
                results.append(
                    RailResult(
                        code="PARALLEL_CANCELLED",
                        action=RailAction.OBSERVE,
                        reason="Rails pendentes cancelados por fail-fast.",
                        metadata={"cancelled_codes": execution.cancelled_codes},
                    )
                )
        else:
            results = []
            for rail in self.rails:
                code = getattr(rail, "code", rail.__class__.__name__)
                try:
                    raw = await rail.evaluate(candidate, ctx)
                    results.append(self._normalize_result(raw, candidate=candidate))
                except Exception as exc:
                    logger.exception("output_supervisor.rail_failed code=%s", code)
                    results.append(
                        RailResult(
                            code=str(code),
                            action=self.fail_closed_action,
                            reason=f"Rail falhou em modo fail-closed: {exc}",
                            metadata={"exception_type": exc.__class__.__name__},
                        )
                    )

        decision = self.aggregate(candidate, list(results), ctx)
        await self._emit_events(results, decision, ctx)
        await self._emit_final(decision, ctx)
        return decision

    def aggregate(self, candidate: str, results: list[RailResult], context: dict[str, Any] | None = None) -> RailDecisionV2:
        ctx = context or {}
        final_action = max((r.action for r in results), key=lambda a: _SEVERITY.get(a, 0), default=RailAction.ALLOW)

        sanitized = candidate
        for result in results:
            if result.action == RailAction.SANITIZE and result.sanitized_text is not None:
                sanitized = result.sanitized_text

        guidance_parts = [r.guidance for r in results if r.guidance]
        if final_action == RailAction.RETRY and int(ctx.get("supervisor_attempt", 0)) >= self.max_retries:
            final_action = RailAction.HANDOVER
            guidance_parts.append("Limite de retries do supervisor atingido.")

        handover_reason = "; ".join(r.reason for r in results if r.action == RailAction.HANDOVER and r.reason)
        return RailDecisionV2(
            action=final_action,
            results=results,
            candidate=sanitized if final_action in {RailAction.ALLOW, RailAction.SANITIZE, RailAction.OBSERVE} else candidate,
            guidance="\n".join(guidance_parts),
            fallback_message=self.fallback_message,
            handover_reason=handover_reason,
            metadata={"max_severity": _SEVERITY.get(final_action, 0)},
        )

    def _normalize_result(self, raw: Any, *, candidate: str) -> RailResult:
        if isinstance(raw, RailResult):
            return raw

        if isinstance(raw, LegacyRailDecision):
            if raw.allowed and raw.sanitized_text is not None:
                action = RailAction.SANITIZE
            elif raw.allowed:
                action = RailAction.ALLOW
            else:
                code = (raw.code or "").upper()
                if code in {"REVPREC", "CMP", "SCO", "GND"}:
                    action = RailAction.RETRY
                elif code in {"HANDOVER", "ATH", "HUMAN"}:
                    action = RailAction.HANDOVER
                else:
                    action = RailAction.BLOCK
            return RailResult(
                code=raw.code,
                action=action,
                reason=raw.reason,
                guidance=raw.metadata.get("guidance", raw.reason) if raw.metadata else raw.reason,
                sanitized_text=raw.sanitized_text,
                metadata=dict(raw.metadata or {}),
            )

        if isinstance(raw, dict):
            action_value = raw.get("action", "allow")
            return RailResult(
                code=str(raw.get("code", "DICT_RAIL")),
                action=RailAction(action_value),
                reason=str(raw.get("reason", "")),
                guidance=str(raw.get("guidance", "")),
                sanitized_text=raw.get("sanitized_text"),
                metadata=dict(raw.get("metadata", {}) or {}),
            )

        return RailResult(code="UNKNOWN_RAIL", action=RailAction.ALLOW, metadata={"raw_type": raw.__class__.__name__})

    async def apply(self, candidate: str, context: dict[str, Any] | None = None) -> str:
        """Atalho para canais simples que não precisam manipular retry/handover."""
        decision = await self.evaluate(candidate, context)
        if decision.action in {RailAction.ALLOW, RailAction.SANITIZE, RailAction.OBSERVE}:
            return decision.candidate
        if decision.action == RailAction.RETRY:
            return decision.fallback_message
        if decision.action == RailAction.HANDOVER:
            return "Vou encaminhar seu atendimento para continuidade com um especialista."
        return decision.fallback_message

    def _is_suppressed_legacy_code(self, rail_code: str | None) -> bool:
        code = str(rail_code or "").strip().upper()
        return code in {"LEGACY_OUTPUT_GUARDRAIL", "LEGACY_OUTPUT_GUARDRAILS", "LLM_GUARDRAIL", "LLM_GRL"}

    async def _emit(self, event_type: str, payload: dict[str, Any], context: dict[str, Any]) -> None:
        if not self.observer:
            return
        try:
            await self.observer.emit(event_type, {**context, **payload}, metadata={"component": "output_supervisor"})
        except Exception:
            logger.debug("output_supervisor.emit_failed event_type=%s", event_type, exc_info=True)

    async def _emit_events(self, results: list[RailResult], decision: RailDecisionV2, context: dict[str, Any]) -> None:
        for result in results:
            if self._is_suppressed_legacy_code(result.code):
                continue
            event = {
                RailAction.ALLOW: "GRL.002",
                RailAction.SANITIZE: "GRL.003",
                RailAction.BLOCK: "GRL.004",
                RailAction.RETRY: "GRL.005",
                RailAction.HANDOVER: "GRL.006",
                RailAction.OBSERVE: "GRL.007",
            }.get(result.action, "GRL.007")
            rail_code = str(result.code or "UNKNOWN").upper()
            allowed = result.action in {RailAction.ALLOW, RailAction.SANITIZE, RailAction.OBSERVE}
            payload = {
                "stage": "output",
                "phase": "output",
                "component": "guardrail",
                "rail_code": rail_code,
                "code": rail_code,
                "action": result.action.value,
                "allowed": allowed,
                "approved": allowed,
                "reason": result.reason,
                "metadata": result.metadata,
            }
            await self._emit(event, payload, context)

            # Emit named guardrail events too, so Langfuse can be searched by
            # the concrete rail name, e.g. REVPREC, instead of only GRL.005.
            # Legacy catch-all output rails are intentionally suppressed because
            # they duplicate the calibrated GRL signal and add no business value.
            if not self._is_suppressed_legacy_code(rail_code):
                await self._emit(f"guardrail.output.{rail_code}.completed", payload, context)
                await self._emit(f"GRL.{rail_code}", payload, context)

    async def _emit_final(self, decision: RailDecisionV2, context: dict[str, Any]) -> None:
        await self._emit(
            "GRL.009",
            {
                "action": decision.action.value,
                "approved": decision.approved,
                "guidance": decision.guidance,
                "handover_reason": decision.handover_reason,
            },
            context,
        )
