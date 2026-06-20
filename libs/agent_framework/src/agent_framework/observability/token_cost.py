from __future__ import annotations

"""Token and cost accounting utilities.

This module is intentionally provider-neutral. It accepts OpenAI-style objects,
LangChain metadata, OCI/Cohere-like dictionaries, and plain dictionaries. The
output is stable and can be persisted in UsageRepository and attached to
Langfuse generations.
"""

import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_openai_usage(cls, usage: Any) -> "TokenUsage":
        if not usage:
            return cls()
        if hasattr(usage, "model_dump"):
            usage = usage.model_dump()
        elif hasattr(usage, "dict"):
            usage = usage.dict()
        elif not isinstance(usage, dict):
            usage = {k: getattr(usage, k) for k in dir(usage) if not k.startswith("_") and k in {
                "prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens",
                "prompt_tokens_details", "completion_tokens_details", "cached_tokens", "reasoning_tokens"
            }}

        prompt_details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
        completion_details = usage.get("completion_tokens_details") or usage.get("output_tokens_details") or {}

        prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or usage.get("inputTokenCount") or 0)
        completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or usage.get("outputTokenCount") or 0)
        cached = int(prompt_details.get("cached_tokens") or usage.get("cached_tokens") or 0)
        reasoning = int(completion_details.get("reasoning_tokens") or usage.get("reasoning_tokens") or 0)
        total = int(usage.get("total_tokens") or usage.get("totalTokenCount") or prompt + completion + reasoning)
        return cls(prompt, completion, cached, reasoning, total)

    def asdict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cached_tokens": self.cached_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class ModelPrice:
    input_per_1m: Decimal
    output_per_1m: Decimal
    cached_input_per_1m: Decimal = Decimal("0")
    reasoning_per_1m: Decimal | None = None
    currency: str = "USD"


DEFAULT_MODEL_PRICES: dict[str, dict[str, str]] = {
    "openai.gpt-4.1": {"input_per_1m": "2.00", "output_per_1m": "8.00", "cached_input_per_1m": "0.50"},
    "gpt-4.1": {"input_per_1m": "2.00", "output_per_1m": "8.00", "cached_input_per_1m": "0.50"},
    "gpt-4.1-mini": {"input_per_1m": "0.40", "output_per_1m": "1.60", "cached_input_per_1m": "0.10"},
    "cohere.command-r-08-2024": {"input_per_1m": "0.50", "output_per_1m": "1.50"},
    "meta.llama-3.1-70b-instruct": {"input_per_1m": "0.50", "output_per_1m": "0.50"},
    "mock-llm": {"input_per_1m": "0", "output_per_1m": "0", "cached_input_per_1m": "0"},
}


class CostTracker:
    def __init__(self, prices: dict[str, dict[str, Any]] | None = None, usd_brl: Decimal | str = Decimal("5.0")):
        self.usd_brl = Decimal(str(usd_brl))
        self.prices: dict[str, ModelPrice] = {}
        for model, price in (prices or DEFAULT_MODEL_PRICES).items():
            self.prices[model] = ModelPrice(
                input_per_1m=Decimal(str(price.get("input_per_1m", 0))),
                output_per_1m=Decimal(str(price.get("output_per_1m", 0))),
                cached_input_per_1m=Decimal(str(price.get("cached_input_per_1m", 0))),
                reasoning_per_1m=Decimal(str(price["reasoning_per_1m"])) if price.get("reasoning_per_1m") is not None else None,
                currency=str(price.get("currency", "USD")),
            )

    def calculate(self, model: str, usage: TokenUsage) -> dict[str, Any]:
        price = self.prices.get(model) or self.prices.get(model.split(":")[-1]) or ModelPrice(Decimal("0"), Decimal("0"))
        non_cached = max(usage.prompt_tokens - usage.cached_tokens, 0)
        reasoning_rate = price.reasoning_per_1m if price.reasoning_per_1m is not None else price.output_per_1m
        cost_usd = (
            Decimal(non_cached) / Decimal(1_000_000) * price.input_per_1m
            + Decimal(usage.cached_tokens) / Decimal(1_000_000) * price.cached_input_per_1m
            + Decimal(usage.completion_tokens) / Decimal(1_000_000) * price.output_per_1m
            + Decimal(usage.reasoning_tokens) / Decimal(1_000_000) * reasoning_rate
        )
        cost_usd = cost_usd.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        cost_brl = (cost_usd * self.usd_brl).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        return {"model": model, "cost_usd": float(cost_usd), "cost_brl": float(cost_brl), **usage.asdict()}


class TokenUsageCollector:
    def __init__(self, settings=None):
        prices = None
        if settings and getattr(settings, "MODEL_PRICES_JSON", None):
            prices = json.loads(settings.MODEL_PRICES_JSON)
        self.cost_tracker = CostTracker(prices=prices, usd_brl=getattr(settings, "USD_BRL_RATE", "5.0") if settings else "5.0")

    def enrich(self, model: str, usage_obj: Any) -> dict[str, Any]:
        usage = TokenUsage.from_openai_usage(usage_obj)
        return self.cost_tracker.calculate(model, usage)
