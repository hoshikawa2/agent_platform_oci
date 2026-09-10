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
    """Deterministic planner constrained by routing.yaml.

    The planner never invents agents or tools. It recognizes independently
    configured intents in conjunction-separated clauses. Execution remains
    owned by the agent/workflow runtime.
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
        # Regra técnica geral: uma mutação que exige o contrato transacional é a
        # operação primária. Não é necessário cadastrar cada par de intents.
        transactional = [item for item in operations if self._is_transactional(item)]
        if len(transactional) == 1:
            primary_operation = transactional[0]
            operations.sort(key=lambda item: item is not primary_operation)
        for operation in operations[1:]:
            if self._is_transactional(operation) and operation.disposition == "execute":
                operation.disposition = "defer"
        for clause in unknown_clauses[: max(0, self.max_operations - len(operations))]:
            operations.append(self._off_context(clause, f"op-{len(operations) + 1}"))
        return MultiIntentPlan(
            plan_id=f"mip-{uuid.uuid4().hex}", operations=operations,
            execution_mode="primary_with_secondary",
        )

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
        match = self._CONFIRM_WITH_REMAINDER.match(str(text or ""))
        if match is None:
            return None
        clause = match.group(1).strip()
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
