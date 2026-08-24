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
from .framework_llm_client import classify_with_framework_llm
from agent_framework.observability.code_mapper import ObservabilityCodeMapper, create_observability_code_mapper

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
    """Supervisor de qualidade de saída, alinhado à fundação de guardrails do framework.

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
        observability_mapper: ObservabilityCodeMapper | None = None,
    ):
        self.guardrails_config = load_guardrails_config(config_path)
        self.config_loaded = bool(self.guardrails_config.loaded)

        # guardrails.yaml is the source of truth when present. The OutputSupervisor
        # used to start with an empty rail list unless the caller manually passed
        # rails, while GuardrailPipeline correctly loaded the YAML. Keep output
        # execution aligned with the same declarative source of truth.
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
        supervisor_cfg = dict(self.guardrails_config.supervisor or {})
        self.fallback_message = fallback_message or supervisor_cfg.get("fallback_message") or "Guardrail validation failed."
        self.handover_message = supervisor_cfg.get("handover_message") or self.fallback_message
        self.max_retries = int(supervisor_cfg.get("max_retries", max_retries))
        self.observer = observer
        self.fail_closed_action = fail_closed_action
        self.enable_parallel = enable_parallel
        self.fail_fast = fail_fast
        self.observability_mapper = observability_mapper or create_observability_code_mapper()
        self.executor = ParallelRailExecutor(
            fail_fast=fail_fast, observer=observer, stage="output",
            observability_mapper=self.observability_mapper,
        )

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
        await self._emit("guardrail.output_supervisor.started", {"stage": "output", "rails": visible_rails}, ctx)

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
                    results.append(self._apply_rail_policy(self._normalize_result(raw, candidate=candidate), rail))
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

        # Remediation is capability-driven, never selected by a rail name.
        # A rail may declare metadata.remediation or YAML policy.on_block.
        rewrite_result = next(
            (r for r in results if r.action == RailAction.BLOCK and self._remediation_type(r) == "rewrite"),
            None,
        )
        other_impediments = [
            r for r in results
            if r is not rewrite_result and r.action in {RailAction.BLOCK, RailAction.RETRY, RailAction.HANDOVER}
        ]
        if rewrite_result is not None and not other_impediments:
            remediation = self._remediation_config(rewrite_result)
            max_attempts = int(remediation.get("max_attempts", 1))
            attempt_key = f"__guardrail_rewrite_attempt:{rewrite_result.code}"
            attempt = int(ctx.get(attempt_key, 0))
            if attempt < max_attempts:
                rewritten = await self._rewrite_guardrail(candidate, rewrite_result, ctx, remediation)
                if rewritten and rewritten.strip() and rewritten.strip() != candidate.strip():
                    rewrite_ctx = dict(ctx)
                    rewrite_ctx[attempt_key] = attempt + 1
                    rewrite_ctx["guardrail_rewrite_original_candidate"] = candidate
                    rewrite_ctx["guardrail_rewrite_original_reason"] = rewrite_result.reason
                    decision = await self.evaluate(rewritten.strip(), rewrite_ctx)
                    decision.results.insert(0, RailResult(
                        code=f"{rewrite_result.code}_REWRITE",
                        action=RailAction.OBSERVE,
                        reason=rewrite_result.reason,
                        metadata={
                            "rewritten": True,
                            "original_code": rewrite_result.code,
                            "rewrite_attempt": attempt + 1,
                        },
                    ))
                    decision.metadata = {
                        **dict(decision.metadata or {}),
                        "guardrail_rewritten": True,
                        "guardrail_rewrite_code": rewrite_result.code,
                        "guardrail_rewrite_attempts": attempt + 1,
                    }
                    return decision

        decision = self.aggregate(candidate, list(results), ctx)
        await self._emit_events(results, decision, ctx)
        await self._emit_final(decision, ctx)
        return decision


    def _remediation_config(self, result: RailResult) -> dict[str, Any]:
        raw = dict(result.metadata or {}).get("remediation")
        if isinstance(raw, str):
            return {"type": raw}
        return dict(raw or {}) if isinstance(raw, dict) else {}

    def _remediation_type(self, result: RailResult) -> str:
        return str(self._remediation_config(result).get("type") or "").strip().lower()

    async def _rewrite_guardrail(
        self, candidate: str, result: RailResult, context: dict[str, Any], remediation: dict[str, Any]
    ) -> str | None:
        """Generic LLM rewrite requested by a rail policy/metadata."""
        try:
            rewrite_context = {
                **dict(context or {}),
                "guardrail_code": result.code,
                "guardrail_reason": result.reason,
            }
            prompt_id = str(remediation.get("prompt_id") or "FALLBACK")
            profile_name = str(remediation.get("profile_name") or "grl")
            component_name = str(remediation.get("component_name") or "guardrail.remediation.rewrite")
            generation_name = str(remediation.get("generation_name") or component_name)
            out = await classify_with_framework_llm(
                self.llm, prompt_id, {"text": candidate, "context": rewrite_context},
                profile_name=profile_name, component_name=component_name, generation_name=generation_name,
            )
            rewritten = str(out.get("reason") or out.get("text") or "").strip()
            return rewritten or None
        except Exception:
            logger.exception("output_supervisor.guardrail_rewrite_failed code=%s", result.code)
            return None

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
                requested_action = str((raw.metadata or {}).get("terminal_action") or "").strip().lower()
                try:
                    action = RailAction(requested_action) if requested_action else RailAction.BLOCK
                except Exception:
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


    def _apply_rail_policy(self, result: RailResult, rail: Any) -> RailResult:
        policy = dict(getattr(rail, "_guardrail_policy", {}) or {})
        if result.action == RailAction.BLOCK:
            configured = policy.get("on_deny")
            if isinstance(configured, dict):
                configured = configured.get("action")
            if configured:
                try:
                    result.action = RailAction(str(configured).strip().lower())
                except Exception:
                    logger.warning("invalid guardrail on_deny action code=%s value=%r", result.code, configured)
            if result.action == RailAction.BLOCK:
                mapped_action = self.observability_mapper.action_for(result.code)
                if mapped_action:
                    try:
                        result.action = RailAction(str(mapped_action).strip().lower())
                        if isinstance(result.metadata, dict):
                            result.metadata.setdefault("action_source", "observability_mapping")
                    except Exception:
                        logger.warning("invalid observability mapping action code=%s value=%r", result.code, mapped_action)
        remediation = policy.get("on_block") or policy.get("remediation")
        if not remediation:
            remediation = self.observability_mapper.remediation_for(result.code)
        if remediation and isinstance(result.metadata, dict):
            result.metadata.setdefault("remediation", remediation)
            result.metadata.setdefault("remediation_source", "rail_policy" if (policy.get("on_block") or policy.get("remediation")) else "observability_mapping")
        return result

    async def apply(self, candidate: str, context: dict[str, Any] | None = None) -> str:
        """Atalho para canais simples que não precisam manipular retry/handover."""
        decision = await self.evaluate(candidate, context)
        if decision.action in {RailAction.ALLOW, RailAction.SANITIZE, RailAction.OBSERVE}:
            return decision.candidate
        if decision.action == RailAction.RETRY:
            return decision.fallback_message
        if decision.action == RailAction.HANDOVER:
            return self.handover_message
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
            rail_code = str(result.code or "UNKNOWN").upper()
            allowed = result.action in {RailAction.ALLOW, RailAction.SANITIZE, RailAction.OBSERVE}
            payload = {
                "stage": "output", "phase": "output", "component": "guardrail",
                "rail_code": rail_code, "code": rail_code, "action": result.action.value,
                "allowed": allowed, "approved": allowed, "reason": result.reason,
                "metadata": result.metadata,
            }
            # Semantic events only. Customer/legacy codes belong exclusively to
            # ObservabilityCodeMapper configuration.
            await self._emit(f"guardrail.result.{result.action.value}", payload, context)
            await self._emit(f"guardrail.output.{rail_code.lower()}.completed", payload, context)

    async def _emit_final(self, decision: RailDecisionV2, context: dict[str, Any]) -> None:
        await self._emit(
            "guardrail.output_supervisor.completed",
            {
                "action": decision.action.value,
                "approved": decision.approved,
                "guidance": decision.guidance,
                "handover_reason": decision.handover_reason,
            },
            context,
        )
