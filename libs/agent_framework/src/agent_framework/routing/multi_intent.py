from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from .models import IntentDefinition


class PlannedIntent(BaseModel):
    operation_id: str
    intent: str
    agent: str
    domain: str | None = None
    tools: list[str] = Field(default_factory=list)
    source_text: str = ""
    disposition: Literal["execute", "inform", "unsupported", "defer"] = "execute"
    message: str | None = None
    status: Literal["pending", "completed", "failed", "skipped"] = "pending"


class MultiIntentPlan(BaseModel):
    plan_id: str
    operations: list[PlannedIntent]
    execution_mode: Literal["primary_with_secondary", "sequential"] = "primary_with_secondary"
    status: Literal["planned", "running", "completed", "partially_completed", "failed"] = "planned"


class MultiIntentPlanner:
    """Multi-intent planner constrained by routing.yaml.

    Deterministic recognition is attempted first. Structured semantic output
    can then be validated by :meth:`plan_from_semantic`; the LLM never owns
    agents, domains or tools, which are always hydrated from configured intents.
    Execution remains owned by the agent/workflow runtime.
    """

    _SPLIT = re.compile(r"\s*(?:,|;|\be\b|\bmas\b|\btamb[eé]m\b)\s*", re.I)
    _CONFIRM_WITH_REMAINDER = re.compile(
        r"^\s*(?:sim|s|pode|pode\s+sim|isso\s+mesmo|claro|ok|confirmo)\s*(?:,|;|\be\b)\s*(.+)$",
        re.I,
    )

    def __init__(
        self,
        intents: list[IntentDefinition],
        config: dict[str, Any] | None = None,
        *,
        transactional_tools: set[str] | None = None,
    ):
        self.intents = [item for item in intents if item.enabled]
        self.config = dict(config or {})
        # Multi-intent é capacidade padrão. O bloco opcional só permite limites
        # técnicos/overrides; sua ausência nunca desabilita a detecção.
        self.enabled = bool(self.config.get("enabled", True))
        self.max_operations = max(2, int(self.config.get("max_operations", 4)))
        self.llm_confidence_threshold = float(
            self.config.get("llm_confidence_threshold", 0.65)
        )
        self.transactional_tools = set(transactional_tools or set())

    @staticmethod
    def _normalize(value: str) -> str:
        text = unicodedata.normalize("NFKD", str(value or ""))
        return "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()

    def _intent_for_clause(self, clause: str) -> IntentDefinition | None:
        normalized = self._normalize(clause)
        clause_tokens = set(re.findall(r"[\w]+", normalized, flags=re.UNICODE))
        matches: list[tuple[int, int, IntentDefinition]] = []
        for intent in self.intents:
            for keyword in intent.keywords:
                token = self._normalize(keyword)
                keyword_tokens = re.findall(r"[\w]+", token, flags=re.UNICODE)
                matched = bool(
                    keyword_tokens
                    and (
                        (len(keyword_tokens) == 1 and keyword_tokens[0] in clause_tokens)
                        or (len(keyword_tokens) > 1 and token in normalized)
                    )
                )
                if matched:
                    matches.append((intent.priority, -len(token), intent))
        if not matches:
            return None
        matches.sort(key=lambda item: (item[0], item[1]))
        return matches[0][2]

    def _is_transactional(self, operation: PlannedIntent) -> bool:
        return any(tool in self.transactional_tools for tool in operation.tools)

    def looks_compound(self, text: str) -> bool:
        """Return whether a turn is worth sending to the semantic fallback."""
        clauses = [
            part.strip(" .")
            for part in self._SPLIT.split(str(text or ""))
            if part.strip(" .")
        ]
        if len(clauses) < 2:
            return False
        return any(
            self._looks_like_request(clause) or self._intent_for_clause(clause)
            for clause in clauses
        )

    @classmethod
    def confirmation_remainder(cls, text: str) -> str | None:
        match = cls._CONFIRM_WITH_REMAINDER.match(str(text or ""))
        return match.group(1).strip() if match is not None else None

    @staticmethod
    def needs_semantic_fallback(plan: MultiIntentPlan | None) -> bool:
        return plan is None or any(
            operation.disposition == "unsupported" for operation in plan.operations
        )

    @classmethod
    def _looks_like_request(cls, clause: str) -> bool:
        normalized = cls._normalize(clause)
        return bool(re.search(
            r"\b(quero|preciso|mandar|manda|mande|enviar|envia|envie|gerar|gera|gere|"
            r"alterar|altera|altere|mudar|muda|mude|consultar|consulta|consulte|"
            r"cancelar|cancela|cancele|explicar|explica|explique|mostrar|mostra|mostre|"
            r"falar|comprar)\b",
            normalized,
        ))

    @staticmethod
    def _off_context(clause: str, operation_id: str) -> PlannedIntent:
        return PlannedIntent(
            operation_id=operation_id,
            intent="off_context",
            agent="",
            source_text=clause,
            disposition="unsupported",
            message=f"Sobre {clause}, não consigo ajudar nesta jornada.",
            status="pending",
        )

    def _finalize_operations(
        self, operations: list[PlannedIntent]
    ) -> MultiIntentPlan | None:
        if len(operations) < 2:
            return None
        transactional = [item for item in operations if self._is_transactional(item)]
        if len(transactional) == 1:
            primary_operation = transactional[0]
            operations.sort(key=lambda item: item is not primary_operation)
        for operation in operations[1:]:
            if self._is_transactional(operation) and operation.disposition == "execute":
                operation.disposition = "defer"
        return MultiIntentPlan(
            plan_id=f"mip-{uuid.uuid4().hex}",
            operations=operations[: self.max_operations],
            execution_mode="primary_with_secondary",
        )

    def _semantic_operations(
        self, payload: dict[str, Any], *, allow_single: bool = False
    ) -> list[PlannedIntent] | None:
        try:
            confidence = float(payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            return None
        if confidence < self.llm_confidence_threshold:
            return None
        raw_operations = payload.get("operations")
        if not isinstance(raw_operations, list):
            return None
        catalog = {intent.name: intent for intent in self.intents}
        operations: list[PlannedIntent] = []
        seen: set[str] = set()
        for raw in raw_operations[: self.max_operations]:
            if not isinstance(raw, dict):
                return None
            source_text = str(raw.get("source_text") or "").strip()
            intent_name = str(raw.get("intent") or "").strip()
            if not source_text:
                return None
            if bool(raw.get("unsupported")):
                operations.append(
                    self._off_context(source_text, f"op-{len(operations) + 1}")
                )
                continue
            intent = catalog.get(intent_name)
            # Fail closed: an invented/disabled intent invalidates the semantic
            # plan instead of trusting agent/tool fields supplied by the model.
            if intent is None:
                return None
            if intent.name in seen:
                continue
            seen.add(intent.name)
            operations.append(PlannedIntent(
                operation_id=f"op-{len(operations) + 1}",
                intent=intent.name,
                agent=intent.agent,
                domain=intent.domain,
                tools=list(intent.mcp_tools),
                source_text=source_text,
            ))
        minimum = 1 if allow_single else 2
        if len(operations) < minimum or not any(op.intent in catalog for op in operations):
            return None
        return operations

    def plan_from_semantic(self, payload: dict[str, Any]) -> MultiIntentPlan | None:
        """Validate structured LLM output against the configured intent catalog."""
        if not self.enabled:
            return None
        operations = self._semantic_operations(payload)
        return self._finalize_operations(operations) if operations else None

    def plan_confirmation_from_semantic(
        self,
        payload: dict[str, Any],
        *,
        primary_intent: str,
        primary_agent: str,
    ) -> MultiIntentPlan | None:
        """Validate one semantic secondary while preserving an open transaction."""
        if not self.enabled:
            return None
        secondary = self._semantic_operations(payload, allow_single=True)
        if not secondary or len(secondary) != 1 or secondary[0].intent == primary_intent:
            return None
        primary = next((item for item in self.intents if item.name == primary_intent), None)
        operations = [PlannedIntent(
            operation_id="op-1",
            intent=primary_intent,
            agent=primary_agent,
            domain=primary.domain if primary else None,
            tools=list(primary.mcp_tools) if primary else [],
            source_text="confirmation",
        ), secondary[0].model_copy(update={"operation_id": "op-2"})]
        return self._finalize_operations(operations)

    def plan(self, text: str) -> MultiIntentPlan | None:
        if not self.enabled:
            return None
        clauses = [part.strip(" .") for part in self._SPLIT.split(str(text or "")) if part.strip(" .")]
        operations: list[PlannedIntent] = []
        unknown_clauses: list[str] = []
        seen: set[str] = set()
        for clause in clauses[: self.max_operations * 2]:
            intent = self._intent_for_clause(clause)
            if intent is None:
                if self._looks_like_request(clause):
                    unknown_clauses.append(clause)
                continue
            if intent.name in seen:
                continue
            seen.add(intent.name)
            operations.append(PlannedIntent(
                operation_id=f"op-{len(operations) + 1}", intent=intent.name,
                agent=intent.agent, domain=intent.domain, tools=list(intent.mcp_tools),
                source_text=clause,
            ))
        if not operations or len(operations) + len(unknown_clauses) < 2:
            return None
        for clause in unknown_clauses[: max(0, self.max_operations - len(operations))]:
            operations.append(self._off_context(clause, f"op-{len(operations) + 1}"))
        return self._finalize_operations(operations)

    def plan_confirmation_secondary(
        self, text: str, *, primary_intent: str, primary_agent: str
    ) -> MultiIntentPlan | None:
        """Recognize an explicit confirmation followed by another request.

        The confirmation remains authoritative for the open transaction. The
        secondary request is recorded and governed by the same combination
        policy instead of turning the whole utterance into an intent shift.
        """
        if not self.enabled:
            return None
        clause = self.confirmation_remainder(text)
        if clause is None:
            return None
        secondary = self._intent_for_clause(clause)
        primary = next((item for item in self.intents if item.name == primary_intent), None)
        if secondary is not None and secondary.name == primary_intent:
            return None
        if secondary is None and not self._looks_like_request(clause):
            return None
        operations = [
            PlannedIntent(
                operation_id="op-1", intent=primary_intent, agent=primary_agent,
                domain=primary.domain if primary else None,
                tools=list(primary.mcp_tools) if primary else [],
                source_text="confirmation", status="pending",
            ),
            (PlannedIntent(
                operation_id="op-2", intent=secondary.name, agent=secondary.agent,
                domain=secondary.domain, tools=list(secondary.mcp_tools), source_text=clause,
            ) if secondary is not None else self._off_context(clause, "op-2")),
        ]
        if self._is_transactional(operations[1]) and operations[1].disposition == "execute":
            operations[1].disposition = "defer"
        return MultiIntentPlan(
            plan_id=f"mip-{uuid.uuid4().hex}", operations=operations,
            execution_mode="primary_with_secondary",
        )

    @staticmethod
    def public_messages(plan: dict[str, Any] | MultiIntentPlan | None) -> list[str]:
        if plan is None:
            return []
        data = plan.model_dump() if isinstance(plan, MultiIntentPlan) else plan
        messages = []
        for operation in data.get("operations", []) or []:
            message = str(operation.get("message") or "").strip()
            if message and message not in messages:
                messages.append(message)
        return messages
