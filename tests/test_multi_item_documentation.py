from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_multi_item_guide_documents_runtime_contract():
    text = (ROOT / "docs" / "MCP_MULTI_ITEM_DEVELOPER_GUIDE.md").read_text(encoding="utf-8")
    for token in (
        "não exige `array/list`",
        "subject",
        "resolved_arguments",
        "results[]",
        "PARTIAL_SUCCESS",
        "workflow.output[tool_name].results",
        "eligible: false",
        "Não faça loop de negócio no agente.",
    ):
        assert token in text


def test_multi_item_guide_is_discoverable_from_main_entry_points():
    for path in (
        ROOT / "README.md",
        ROOT / "Documentacao" / "README_MCP.md",
        ROOT / "docs" / "developer" / "pt" / "INDEX_DEVELOPER_GUIDE.md",
        ROOT / "templates" / "agent_template_backend" / "README.md",
    ):
        assert "MCP_MULTI_ITEM" in path.read_text(encoding="utf-8") or "MCP multi-item" in path.read_text(encoding="utf-8") or "MCP Multi-item" in path.read_text(encoding="utf-8")


def test_multi_item_is_discoverable_from_tuning_performance():
    tuning_index = (ROOT / "Tuning-Performance" / "README.md").read_text(encoding="utf-8")
    tuning_readme = (ROOT / "Tuning-Performance" / "Multi_Item_MCP" / "README.md").read_text(encoding="utf-8")
    implementation = (ROOT / "Tuning-Performance" / "Multi_Item_MCP" / "IMPLEMENTACAO_MULTI_ITEM_MCP.md").read_text(encoding="utf-8")

    assert "Multi_Item_MCP" in tuning_index
    for token in (
        "tools.yaml",
        "tool_policies.yaml",
        "results[]",
        "PARTIAL_SUCCESS",
        "NÃO cria motor multi-item",
    ):
        assert token in tuning_readme

    for token in (
        "MCP Server ou workflow",
        "success",
        "PARTIAL_SUCCESS",
        "Checklist do desenvolvedor",
    ):
        assert token in implementation
