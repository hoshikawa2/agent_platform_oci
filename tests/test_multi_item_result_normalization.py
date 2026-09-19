from agent_framework.runtime.agent_runtime import AgentRuntimeMixin


def _workflow_result(*, items, ok=False, error="secondary step failed"):
    return {
        "tool_name": "cancelar_vas_avulso",
        "ok": ok,
        "result": {
            "status": "COMPLETED",
            "output": {
                "cancelar_vas_avulso": {
                    "success": all(bool(item.get("success")) for item in items),
                    "results": items,
                },
                "secondary_step": {"success": False, "error": error},
            },
        },
        "error": error,
        "metadata": {"workflow_status": "COMPLETED"},
    }


def test_multi_item_partial_success_preserves_successful_items():
    raw = _workflow_result(items=[
        {"subject": "A", "success": True},
        {"subject": "B", "success": False, "reason": "not_found"},
        {"subject": "C", "success": True},
    ])

    result = AgentRuntimeMixin._normalize_multi_item_tool_result("cancelar_vas_avulso", raw)

    assert result["ok"] is True
    assert result["original_ok"] is False
    assert result["partial_success"] is True
    assert result["multi_item_status"] == "PARTIAL_SUCCESS"
    assert result["metadata"]["multi_item"] == {
        "status": "PARTIAL_SUCCESS",
        "items_count": 3,
        "items_succeeded_count": 2,
        "items_failed_count": 1,
        "primary_tool": "cancelar_vas_avulso",
    }
    assert result["secondary_error"] == "secondary step failed"
    assert raw["ok"] is False  # normalizer is non-mutating


def test_multi_item_primary_success_is_not_overwritten_by_secondary_composite_failure():
    raw = _workflow_result(items=[
        {"subject": "TIM Fashion Mensal", "success": True},
        {"subject": "Aya Audiobooks Premium", "success": True},
        {"subject": "Neymar Jr", "success": True},
    ], error="Item ausente em validação posterior")

    result = AgentRuntimeMixin._normalize_multi_item_tool_result("cancelar_vas_avulso", raw)

    assert result["ok"] is True
    assert result["multi_item_status"] == "SUCCESS"
    assert result["partial_success"] is False
    assert result["metadata"]["multi_item"]["items_succeeded_count"] == 3
    assert result["secondary_error"] == "Item ausente em validação posterior"


def test_single_item_result_does_not_change_existing_semantics():
    raw = _workflow_result(items=[{"subject": "A", "success": True}])
    result = AgentRuntimeMixin._normalize_multi_item_tool_result("cancelar_vas_avulso", raw)
    assert result == raw


def test_unrelated_nested_results_do_not_override_primary_tool_failure():
    raw = {
        "tool_name": "cancelar_vas_avulso",
        "ok": False,
        "result": {
            "status": "COMPLETED",
            "output": {
                "other_tool": {
                    "results": [
                        {"subject": "A", "success": True},
                        {"subject": "B", "success": True},
                    ]
                }
            },
        },
        "error": "primary tool failed",
    }
    result = AgentRuntimeMixin._normalize_multi_item_tool_result("cancelar_vas_avulso", raw)
    assert result == raw
