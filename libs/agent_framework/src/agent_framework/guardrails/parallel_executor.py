from __future__ import annotations

"""Execução paralela de guardrails com fail-fast.

Este módulo mantém compatibilidade com os rails legados do framework
(`Guardrail.evaluate() -> RailDecision`) e com rails novos que retornam
`RailResult`. A ideia é economizar latência: rails bloqueantes podem rodar em
paralelo e, quando o primeiro veredito terminal aparece, os demais são
cancelados. Rails observacionais podem ser executados em outra rodada sem
cancelamento para preservar telemetria.
"""

import asyncio
import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from .base import RailDecision as LegacyRailDecision
from .rail_action import RailAction
from .rail_result import RailResult

logger = logging.getLogger("agent_framework.guardrails.parallel_executor")

TERMINAL_ACTIONS: set[RailAction] = {RailAction.BLOCK, RailAction.RETRY, RailAction.HANDOVER}
ALLOW_ACTIONS: set[RailAction] = {RailAction.ALLOW, RailAction.SANITIZE, RailAction.OBSERVE}


@dataclass(slots=True)
class ParallelRailExecution:
    """Resultado detalhado de uma rodada de execução paralela."""

    text: str
    results: list[RailResult] = field(default_factory=list)
    legacy_decisions: list[LegacyRailDecision] = field(default_factory=list)
    cancelled_codes: list[str] = field(default_factory=list)
    terminal_result: RailResult | None = None
    fail_fast_triggered: bool = False

    @property
    def blocked(self) -> bool:
        return bool(self.terminal_result and self.terminal_result.action in TERMINAL_ACTIONS)


class ParallelRailExecutor:
    """Executor oficial para rails em paralelo.

    Parâmetros principais:
    - fail_fast: cancela pendentes no primeiro resultado terminal.
    - terminal_actions: ações que encerram a rodada quando fail_fast=True.
    - fail_closed: exceção em rail vira BLOCK por segurança.

    Observação: `asyncio.Task.cancel()` só interrompe cooperativamente. Rails
    com trabalho CPU-bound síncrono devem ser mantidos curtos ou movidos para
    executor/thread próprio dentro do rail.
    """

    def __init__(
        self,
        *,
        fail_fast: bool = True,
        terminal_actions: set[RailAction] | None = None,
        fail_closed: bool = True,
        observer: Any | None = None,
        stage: str = "guardrail",
    ) -> None:
        self.fail_fast = fail_fast
        self.terminal_actions = terminal_actions or TERMINAL_ACTIONS
        self.fail_closed = fail_closed
        self.observer = observer
        self.stage = stage

    async def run(
        self,
        text: str,
        context: dict[str, Any] | None,
        rails: Sequence[Any] | Iterable[Any],
        *,
        fail_fast: bool | None = None,
        stage: str | None = None,
    ) -> ParallelRailExecution:
        ctx = dict(context or {})
        rail_list = list(rails or [])
        current_stage = stage or self.stage
        use_fail_fast = self.fail_fast if fail_fast is None else fail_fast
        execution = ParallelRailExecution(text=text)

        if not rail_list:
            return execution

        visible_rails = [self._code(r) for r in rail_list if not self._is_suppressed_legacy_code(self._code(r))]
        await self._emit_grl("001", {"stage": current_stage, "rails": visible_rails}, ctx)

        tasks: dict[asyncio.Task[RailResult], Any] = {
            asyncio.create_task(self._run_one(rail, text, ctx, current_stage), name=f"rail:{self._code(rail)}"): rail
            for rail in rail_list
        }

        pending: set[asyncio.Task[RailResult]] = set(tasks)
        try:
            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    rail = tasks[task]
                    code = self._code(rail)
                    try:
                        result = task.result()
                    except asyncio.CancelledError:
                        execution.cancelled_codes.append(code)
                        continue
                    except Exception as exc:  # defesa adicional; _run_one já converte
                        logger.exception("parallel rail task failed code=%s", code)
                        result = RailResult(
                            code=code,
                            action=RailAction.BLOCK if self.fail_closed else RailAction.OBSERVE,
                            reason=f"Rail falhou: {exc}",
                            metadata={"exception_type": exc.__class__.__name__},
                        )

                    execution.results.append(result)
                    legacy_model = result.metadata.get("legacy_decision_model") if isinstance(result.metadata, dict) else None
                    if isinstance(legacy_model, dict):
                        try:
                            execution.legacy_decisions.append(LegacyRailDecision(**legacy_model))
                        except Exception:
                            logger.debug("could not rebuild legacy decision code=%s", code, exc_info=True)

                    await self._emit_result(result, current_stage, ctx)

                    if use_fail_fast and result.action in self.terminal_actions:
                        execution.terminal_result = result
                        execution.fail_fast_triggered = True
                        for pending_task in pending:
                            pending_rail = tasks[pending_task]
                            execution.cancelled_codes.append(self._code(pending_rail))
                            pending_task.cancel()
                        if pending:
                            await asyncio.gather(*pending, return_exceptions=True)
                        pending = set()
                        break
        finally:
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        # Sanitizações devem ser aplicadas em ordem estável de configuração, não
        # na ordem de conclusão, para preservar previsibilidade.
        sanitized = text
        result_by_code = {r.code: r for r in execution.results}
        for rail in rail_list:
            result = result_by_code.get(self._code(rail))
            if result and result.action == RailAction.SANITIZE and result.sanitized_text is not None:
                sanitized = result.sanitized_text
        execution.text = sanitized

        if execution.terminal_result is None:
            for result in execution.results:
                if result.action in self.terminal_actions:
                    execution.terminal_result = result
                    break

        await self._emit_grl(
            "009",
            {
                "stage": current_stage,
                "result_count": len(execution.results),
                "cancelled_codes": execution.cancelled_codes,
                "fail_fast_triggered": execution.fail_fast_triggered,
                "terminal_code": execution.terminal_result.code if execution.terminal_result else None,
                "terminal_action": execution.terminal_result.action.value if execution.terminal_result else None,
            },
            ctx,
        )
        return execution

    async def _run_one(self, rail: Any, text: str, context: dict[str, Any], stage: str | None = None) -> RailResult:
        code = self._code(rail)
        current_stage = stage or self.stage
        await self._emit_rail_event(
            "started",
            code,
            current_stage,
            context,
            {
                "text_size": len(text or ""),
                "component": "guardrail",
            },
        )
        try:
            raw = rail.evaluate(text, context)
            if inspect.isawaitable(raw):
                raw = await raw
            result = self._normalize(raw, code=code)
            await self._emit_rail_event(
                "completed",
                result.code or code,
                current_stage,
                context,
                {
                    "action": result.action.value,
                    "allowed": result.action in ALLOW_ACTIONS,
                    "approved": result.action in ALLOW_ACTIONS,
                    "reason": result.reason,
                    "metadata": result.metadata,
                    "component": "guardrail",
                },
            )
            return result
        except asyncio.CancelledError:
            await self._emit_rail_event(
                "cancelled",
                code,
                current_stage,
                context,
                {"component": "guardrail"},
            )
            raise
        except Exception as exc:
            logger.exception("parallel rail failed code=%s", code)
            result = RailResult(
                code=code,
                action=RailAction.BLOCK if self.fail_closed else RailAction.OBSERVE,
                reason=f"Rail falhou em modo {'fail-closed' if self.fail_closed else 'observe'}: {exc}",
                metadata={"exception_type": exc.__class__.__name__},
            )
            await self._emit_rail_event(
                "completed",
                code,
                current_stage,
                context,
                {
                    "action": result.action.value,
                    "allowed": result.action in ALLOW_ACTIONS,
                    "approved": result.action in ALLOW_ACTIONS,
                    "reason": result.reason,
                    "metadata": result.metadata,
                    "component": "guardrail",
                },
            )
            return result

    def _normalize(self, raw: Any, *, code: str) -> RailResult:
        if isinstance(raw, RailResult):
            return raw
        if isinstance(raw, LegacyRailDecision):
            if raw.allowed and raw.sanitized_text is not None:
                action = RailAction.SANITIZE
            elif raw.allowed:
                # Risco/telemetria que não altera fluxo fica como OBSERVE quando
                # metadata indica algum achado, senão ALLOW.
                action = RailAction.OBSERVE if raw.metadata else RailAction.ALLOW
            else:
                normalized_code = (raw.code or code or "").upper()
                if normalized_code in {"REVPREC", "CMP", "SCO", "GND"}:
                    action = RailAction.RETRY
                elif normalized_code in {"HANDOVER", "ATH", "HUMAN"}:
                    action = RailAction.HANDOVER
                else:
                    action = RailAction.BLOCK
            return RailResult(
                code=raw.code or code,
                action=action,
                reason=raw.reason,
                guidance=raw.metadata.get("guidance", raw.reason) if raw.metadata else raw.reason,
                sanitized_text=raw.sanitized_text,
                metadata={**dict(raw.metadata or {}), "legacy_decision_model": raw.model_dump()},
            )
        if isinstance(raw, dict):
            action_value = raw.get("action", "allow")
            return RailResult(
                code=str(raw.get("code") or code),
                action=RailAction(action_value),
                reason=str(raw.get("reason", "")),
                guidance=str(raw.get("guidance", "")),
                sanitized_text=raw.get("sanitized_text"),
                metadata=dict(raw.get("metadata", {}) or {}),
            )
        return RailResult(code=code, action=RailAction.ALLOW, metadata={"raw_type": raw.__class__.__name__})

    def _code(self, rail: Any) -> str:
        return str(getattr(rail, "code", rail.__class__.__name__))

    async def _emit_result(self, result: RailResult, stage: str, context: dict[str, Any]) -> None:
        if self._is_suppressed_legacy_code(result.code):
            return
        event_code = {
            RailAction.ALLOW: "002",
            RailAction.SANITIZE: "003",
            RailAction.BLOCK: "004",
            RailAction.RETRY: "005",
            RailAction.HANDOVER: "006",
            RailAction.OBSERVE: "007",
        }.get(result.action, "007")
        payload = {
            "stage": stage,
            "rail_code": result.code,
            "code": result.code,
            "action": result.action.value,
            "allowed": result.action in ALLOW_ACTIONS,
            "approved": result.action in ALLOW_ACTIONS,
            "reason": result.reason,
            "metadata": result.metadata,
            "component": "guardrail",
        }
        await self._emit_grl(event_code, payload, context)
        await self._emit_named_grl(result.code, payload, context)

    async def _emit_rail_event(
        self,
        status: str,
        rail_code: str,
        stage: str,
        context: dict[str, Any],
        payload: dict[str, Any] | None = None,
    ) -> None:
        if not self.observer:
            return
        code = str(rail_code or "UNKNOWN").upper()
        if self._is_suppressed_legacy_code(code):
            return
        event_type = f"guardrail.{stage}.{code}.{status}"
        body = {
            **context,
            **dict(payload or {}),
            "stage": stage,
            "phase": "output" if "output" in str(stage).lower() else "input",
            "rail_code": code,
            "code": code,
            "status": status,
        }
        try:
            await self.observer.emit(event_type, body, metadata={"component": "guardrail", "rail_code": code})
        except Exception:
            logger.debug("parallel executor named rail emit failed code=%s status=%s", code, status, exc_info=True)

    def _is_suppressed_legacy_code(self, rail_code: str | None) -> bool:
        code = str(rail_code or "").strip().upper()
        return code in {"LEGACY_OUTPUT_GUARDRAIL", "LEGACY_OUTPUT_GUARDRAILS", "LLM_GUARDRAIL", "LLM_GRL"}

    async def _emit_named_grl(self, rail_code: str, payload: dict[str, Any], context: dict[str, Any]) -> None:
        if not self.observer:
            return
        code = str(rail_code or "").strip().upper()
        if not code or self._is_suppressed_legacy_code(code):
            return
        try:
            if hasattr(self.observer, "emit_grl"):
                await self.observer.emit_grl(code, {**context, **payload, "rail_code": code, "code": code}, component="parallel_rail_executor")
            else:
                await self.observer.emit(f"GRL.{code}", {**context, **payload, "rail_code": code, "code": code}, metadata={"component": "parallel_rail_executor"})
        except Exception:
            logger.debug("parallel executor named GRL emit failed code=%s", code, exc_info=True)

    async def _emit_grl(self, code: str, payload: dict[str, Any], context: dict[str, Any]) -> None:
        if not self.observer:
            return
        try:
            if hasattr(self.observer, "emit_grl"):
                await self.observer.emit_grl(code, {**context, **payload}, component="parallel_rail_executor")
            else:
                await self.observer.emit(f"GRL.{code}", {**context, **payload}, metadata={"component": "parallel_rail_executor"})
        except Exception:
            logger.debug("parallel executor emit failed code=%s", code, exc_info=True)
