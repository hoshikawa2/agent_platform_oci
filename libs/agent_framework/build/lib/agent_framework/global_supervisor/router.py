from __future__ import annotations

import json
import logging
import re
from typing import Any

from .config import BackendRegistry
from .models import BackendDefinition, GlobalRouteDecision, GlobalRouteRequest, RoutingMode
from .session_store import InMemoryGlobalSessionStore

logger = logging.getLogger("agent_framework.global_supervisor")

_TERMINAL_WORDS = {
    "obrigado", "obrigada", "valeu", "tchau", "encerrar", "fim", "cancelar atendimento"
}


class GlobalSupervisorRouter:
    """Roteador global entre backends.

    Modos:
    - router: usa regras/keywords/domínios do YAML.
    - supervisor: usa LLM para escolher backend.
    - hybrid: mantém backend ativo quando coerente; usa router; chama LLM quando ambíguo.
    """

    def __init__(
        self,
        registry: BackendRegistry,
        llm: Any | None = None,
        session_store: InMemoryGlobalSessionStore | None = None,
        mode: RoutingMode = "hybrid",
        keep_active_backend: bool = True,
        use_supervisor_on_conflict: bool = True,
        min_router_confidence: float = 0.55,
    ):
        self.registry = registry
        self.llm = llm
        self.session_store = session_store or InMemoryGlobalSessionStore()
        self.mode = mode
        self.keep_active_backend = keep_active_backend
        self.use_supervisor_on_conflict = use_supervisor_on_conflict
        self.min_router_confidence = min_router_confidence

    async def route(self, request: GlobalRouteRequest) -> GlobalRouteDecision:
        mode = request.mode or self.mode
        session_id = self._session_id(request)
        tenant_id = request.tenant_id or request.payload.get("tenant_id") or "default"

        if request.force_backend:
            decision = self._forced_decision(request.force_backend, mode)
            await self.session_store.set_active_backend(session_id, decision.backend_id, tenant_id, forced=True)
            return decision

        state = await self.session_store.get(session_id)
        text = self._extract_text(request).strip()

        if mode == "router":
            decision = self._route_by_rules(text, mode)
        elif mode == "supervisor":
            decision = await self._route_by_llm(text, request, mode)
        else:
            decision = await self._route_hybrid(text, request, state, mode)

        await self.session_store.set_active_backend(
            session_id,
            decision.backend_id,
            tenant_id,
            last_reason=decision.reason,
            last_mode=decision.mode,
            last_confidence=decision.confidence,
        )
        return decision

    async def _route_hybrid(self, text: str, request: GlobalRouteRequest, state, mode: RoutingMode) -> GlobalRouteDecision:
        # Se a conversa já tem backend ativo e a mensagem parece continuação curta, mantenha.
        active_backend = request.current_backend or (state.active_backend if state else None)
        if self.keep_active_backend and active_backend and active_backend in self.registry.backends:
            if self._looks_like_followup(text):
                return GlobalRouteDecision(
                    backend_id=active_backend,
                    confidence=0.78,
                    reason="Mensagem parece continuação; mantendo backend ativo da sessão.",
                    mode=mode,
                    keep_active_backend=True,
                )

        rule_decision = self._route_by_rules(text, mode)
        if rule_decision.confidence >= self.min_router_confidence:
            return rule_decision

        if self.use_supervisor_on_conflict and self.llm:
            llm_decision = await self._route_by_llm(text, request, mode, fallback=rule_decision)
            return llm_decision

        if active_backend and active_backend in self.registry.backends:
            return GlobalRouteDecision(
                backend_id=active_backend,
                confidence=0.50,
                reason="Router ficou ambíguo; mantendo backend ativo por política híbrida.",
                mode=mode,
                keep_active_backend=True,
                candidates=rule_decision.candidates,
            )
        return rule_decision

    def _route_by_rules(self, text: str, mode: RoutingMode) -> GlobalRouteDecision:
        normalized = self._normalize(text)
        scored: list[tuple[float, BackendDefinition, list[str]]] = []
        for backend in self.registry.list():
            hits: list[str] = []
            score = 0.0
            for kw in backend.keywords:
                nkw = self._normalize(kw)
                if nkw and nkw in normalized:
                    hits.append(kw)
                    score += 1.0
            for domain in backend.domains:
                nd = self._normalize(domain)
                if nd and nd in normalized:
                    hits.append(domain)
                    score += 0.7
            if score:
                # prioridade menor aumenta levemente confiança
                score += max(0, (200 - backend.priority)) / 1000
            scored.append((score, backend, hits))

        scored.sort(key=lambda x: (-x[0], x[1].priority, x[1].backend_id))
        best_score, best_backend, hits = scored[0] if scored else (0.0, self.registry.default(), [])
        if best_score <= 0:
            best_backend = self.registry.default()
            confidence = 0.25
            reason = "Nenhuma regra forte encontrada; usando backend default."
        else:
            # normalização simples para 0..1
            confidence = min(0.95, 0.35 + best_score / 4)
            reason = f"Backend escolhido por regras: matches={hits}."
        candidates = [
            {"backend_id": b.backend_id, "score": round(s, 3), "matches": h}
            for s, b, h in scored[:5]
        ]
        return GlobalRouteDecision(
            backend_id=best_backend.backend_id,
            confidence=confidence,
            reason=reason,
            mode=mode,
            used_llm=False,
            candidates=candidates,
        )

    async def _route_by_llm(
        self,
        text: str,
        request: GlobalRouteRequest,
        mode: RoutingMode,
        fallback: GlobalRouteDecision | None = None,
    ) -> GlobalRouteDecision:
        if not self.llm:
            return fallback or self._route_by_rules(text, mode)
        prompt = self._build_supervisor_prompt(text, request)
        try:
            raw = await self.llm.ainvoke([
                {"role": "system", "content": "Você é um supervisor global de backends. Responda somente JSON válido."},
                {"role": "user", "content": prompt},
            ], temperature=0, profile_name="supervisor", component_name="supervisor", generation_name="llm.supervisor")
            data = self._parse_json(raw)
            backend_id = str(data.get("backend") or data.get("backend_id") or "").strip()
            if backend_id not in self.registry.backends:
                raise ValueError(f"LLM retornou backend inválido: {backend_id!r}")
            return GlobalRouteDecision(
                backend_id=backend_id,
                confidence=float(data.get("confidence", 0.75)),
                reason=str(data.get("reason", "Selecionado pelo supervisor LLM.")),
                mode=mode,
                used_llm=True,
                candidates=(fallback.candidates if fallback else []),
                metadata={"raw_llm": raw},
            )
        except Exception as exc:
            logger.exception("Falha no supervisor LLM; usando fallback/router: %s", exc)
            decision = fallback or self._route_by_rules(text, mode)
            decision.reason = f"Fallback após falha do supervisor LLM: {decision.reason}"
            return decision

    def _build_supervisor_prompt(self, text: str, request: GlobalRouteRequest) -> str:
        history = request.payload.get("history") or request.metadata.get("history") or []
        return (
            "Escolha o backend mais adequado para atender a mensagem do usuário.\n\n"
            "Backends disponíveis:\n"
            f"{self.registry.describe_for_prompt()}\n\n"
            "Mensagem atual:\n"
            f"{text}\n\n"
            "Histórico/metadata resumidos:\n"
            f"{json.dumps({'history': history[-6:] if isinstance(history, list) else history, 'metadata': request.metadata}, ensure_ascii=False)[:4000]}\n\n"
            "Retorne somente JSON neste formato:\n"
            '{"backend":"<id>","confidence":0.0,"reason":"..."}'
        )

    def _forced_decision(self, backend_id: str, mode: RoutingMode) -> GlobalRouteDecision:
        self.registry.get(backend_id)
        return GlobalRouteDecision(
            backend_id=backend_id,
            confidence=1.0,
            reason="Backend forçado na requisição.",
            mode=mode,
            used_llm=False,
        )

    def _looks_like_followup(self, text: str) -> bool:
        n = self._normalize(text)
        if not n:
            return True
        if n in _TERMINAL_WORDS:
            return False
        tokens = n.split()
        followup_markers = ["esse", "essa", "isso", "valor", "ele", "ela", "tambem", "e ", "entao", "nesse", "nessa"]
        return len(tokens) <= 6 or any(marker in n for marker in followup_markers)

    def _extract_text(self, request: GlobalRouteRequest) -> str:
        payload = request.payload or {}
        for key in ("text", "message", "input", "user_text"):
            if payload.get(key):
                return str(payload[key])
        if isinstance(payload.get("payload"), dict):
            inner = payload["payload"]
            for key in ("text", "message", "input", "user_text"):
                if inner.get(key):
                    return str(inner[key])
        return str(payload)

    def _session_id(self, request: GlobalRouteRequest) -> str:
        payload = request.payload or {}
        return (
            request.session_id
            or payload.get("session_id")
            or payload.get("conversation_key")
            or request.metadata.get("session_id")
            or "global-default-session"
        )

    def _normalize(self, text: str) -> str:
        text = text.lower()
        text = re.sub(r"[^a-z0-9áàâãéêíóôõúçñ\s]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _parse_json(self, raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        text = str(raw).strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text).strip()
            text = re.sub(r"```$", "", text).strip()
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            text = match.group(0)
        return json.loads(text)
