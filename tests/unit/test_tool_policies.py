from __future__ import annotations

from types import SimpleNamespace

from agent_framework.mcp.tool_policy import ToolPolicyRegistry
from agent_framework.mcp.tool_router import MCPToolRouter


class _Registry:
    def __init__(self, tool=None):
        self.tool = tool

    def get_tool(self, _name):
        return self.tool


def _router(policy_registry, legacy=None):
    router = MCPToolRouter.__new__(MCPToolRouter)
    router.tool_policies = policy_registry
    router.registry = _Registry(legacy)
    return router


def test_missing_policy_file_preserves_legacy_behavior(tmp_path):
    policies = ToolPolicyRegistry(str(tmp_path / "missing.yaml"))
    legacy = SimpleNamespace(
        tool_type="action",
        requires=["order_id"],
        confirmation_required=True,
        execution_policy={},
    )
    router = _router(policies, legacy)

    allowed, reason, metadata = router.validate_execution_policy("alterar", {"order_id": "42"})

    assert allowed is False
    assert "confirmação" in reason
    assert metadata["operation_type"] == "transactional"
    assert metadata["policy_source"] == "tools.yaml"


def test_read_only_policy_executes_without_confirmation(tmp_path):
    path = tmp_path / "tool_policies.yaml"
    path.write_text(
        "tool_policies:\n  consultar:\n    operation_type: read_only\n",
        encoding="utf-8",
    )
    router = _router(ToolPolicyRegistry(str(path)))

    allowed, reason, metadata = router.validate_execution_policy("consultar", {})

    assert allowed is True
    assert reason is None
    assert metadata["operation_type"] == "read_only"


def test_transactional_policy_requires_literal_boolean_confirmation(tmp_path):
    path = tmp_path / "tool_policies.yaml"
    path.write_text(
        "tool_policies:\n  cancelar:\n    operation_type: transactional\n    require_confirmation: true\n",
        encoding="utf-8",
    )
    router = _router(ToolPolicyRegistry(str(path)))

    denied, _, _ = router.validate_execution_policy("cancelar", {"confirmed": "true"})
    allowed, reason, metadata = router.validate_execution_policy("cancelar", {"confirmed": True})

    assert denied is False
    assert allowed is True
    assert reason is None
    assert metadata["policy_source"] == "tool_policies.yaml"


def test_requires_confirmation_alias_is_supported(tmp_path):
    path = tmp_path / "tool_policies.yaml"
    path.write_text(
        "tool_policies:\n  alterar:\n    type: transactional\n    requires_confirmation: true\n",
        encoding="utf-8",
    )

    policy = ToolPolicyRegistry(str(path)).get("alterar")

    assert policy.operation_type == "transactional"
    assert policy.require_confirmation is True
