from types import SimpleNamespace
from agent_framework.observability.token_cost import TokenUsageCollector, TokenUsage


def test_token_usage_extracts_cached_and_reasoning_tokens():
    usage = TokenUsage.from_openai_usage({
        "prompt_tokens": 1000,
        "completion_tokens": 500,
        "total_tokens": 1600,
        "prompt_tokens_details": {"cached_tokens": 250},
        "completion_tokens_details": {"reasoning_tokens": 100},
    })
    assert usage.prompt_tokens == 1000
    assert usage.cached_tokens == 250
    assert usage.reasoning_tokens == 100
    assert usage.total_tokens == 1600


def test_cost_tracker_uses_model_prices_json():
    settings = SimpleNamespace(MODEL_PRICES_JSON='{"my-model":{"input_per_1m":"1","output_per_1m":"2","cached_input_per_1m":"0.1"}}', USD_BRL_RATE='5')
    enriched = TokenUsageCollector(settings).enrich("my-model", {"prompt_tokens": 1000, "completion_tokens": 1000, "prompt_tokens_details": {"cached_tokens": 500}})
    assert enriched["cost_usd"] > 0
    assert abs(enriched["cost_brl"] - enriched["cost_usd"] * 5) < 1e-9
