from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK_SRC = ROOT / "libs" / "agent_framework" / "src"
if str(FRAMEWORK_SRC) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_SRC))

from agent_framework.workflows.models import WorkflowDefinition
from agent_framework.idempotency import create_idempotency_store


PT = ROOT / "docs" / "developer" / "pt"


def _tagged(path: Path, language: str, tag: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"```{language} {re.escape(tag)}\n(.*?)```", text, re.DOTALL)
    assert match, f"bloco {tag!r} ausente em {path}"
    return match.group(1)


@pytest.mark.parametrize(
    ("filename", "tag"),
    [
        ("13_workflows_transacionais_avancados.md", "workflow-actions-example"),
        ("13_workflows_transacionais_avancados.md", "idempotency-example"),
        ("15_apresentacao_recuperacao_e_observabilidade.md", "renderer-example"),
        ("16_multiagente_composicao_e_ciclo_de_vida.md", "agent-runtime-bundle-example"),
    ],
)
def test_python_examples_compile(filename: str, tag: str) -> None:
    source = _tagged(PT / filename, "python", tag)
    ast.parse(source)
    compile(source, f"{filename}:{tag}", "exec")


def test_documented_workflow_is_accepted_by_runtime_model() -> None:
    raw = yaml.safe_load(_tagged(PT / "13_workflows_transacionais_avancados.md", "yaml", "workflow-definition-example"))
    definition = WorkflowDefinition.model_validate(raw)
    assert definition.name == "devolucao_pedido"
    assert definition.version == 1
    assert [node.action for node in definition.nodes] == ["validar_pedido", "registrar_devolucao"]


def test_documented_routing_and_registry_contracts() -> None:
    routing = yaml.safe_load(_tagged(PT / "14_routing_parametros_e_estado_avancados.md", "yaml", "routing-advanced-example"))
    mapping = yaml.safe_load(_tagged(PT / "14_routing_parametros_e_estado_avancados.md", "yaml", "parameter-mapping-example"))
    registry = yaml.safe_load(_tagged(PT / "16_multiagente_composicao_e_ciclo_de_vida.md", "yaml", "agents-registry-example"))

    semantic = routing["router"]["transaction_confirmation"]["semantic_fallback"]
    assert set(semantic["allowed_values"]) == {"SIM", "NAO", "CONTINUAR"}
    assert routing["intents"][0]["mcp_tools"] == ["consultar_saldo", "consultar_movimentacoes"]
    assert mapping["mcp_parameter_mapping"]["tools"]["consultar_movimentacoes"]["extract"]["transaction_id"]["group"] == 1
    assert registry["agents"][0]["agent_id"] == registry["default_agent_id"]


@pytest.mark.asyncio
async def test_documented_idempotency_example_executes_only_once() -> None:
    namespace: dict[str, object] = {}
    exec(_tagged(PT / "13_workflows_transacionais_avancados.md", "python", "idempotency-example"), namespace)
    settings = SimpleNamespace(IDEMPOTENCY_PROVIDER="memory", IDEMPOTENCY_REQUIRE_DURABLE=False)
    store = create_idempotency_store(settings, namespace="return-request")
    calls = 0

    async def invoke():
        nonlocal calls
        calls += 1
        return {"protocol": "DEV-123"}

    first = await namespace["execute_once"](store, "customer-1", "123", invoke)
    second = await namespace["execute_once"](store, "customer-1", "123", invoke)
    assert first == second == {"protocol": "DEV-123"}
    assert calls == 1


def test_documented_renderer_masks_and_formats_output() -> None:
    namespace: dict[str, object] = {}
    exec(_tagged(PT / "15_apresentacao_recuperacao_e_observabilidade.md", "python", "renderer-example"), namespace)
    rendered = namespace["render_balance"](
        tool_name="consultar_saldo",
        result={"account_masked": "****1234", "balance": 42.5, "secret": "must-not-leak"},
        state={},
        agent_label="Financeiro",
    )
    assert rendered == "[Financeiro] Conta ****1234: saldo BRL 42.50."
    assert "must-not-leak" not in rendered


def test_new_chapters_have_english_counterparts_and_are_indexed() -> None:
    pairs = {
        "13_workflows_transacionais_avancados.md": "13_advanced_transactional_workflows.md",
        "14_routing_parametros_e_estado_avancados.md": "14_advanced_routing_parameters_and_state.md",
        "15_apresentacao_recuperacao_e_observabilidade.md": "15_presentation_recovery_and_observability.md",
        "16_multiagente_composicao_e_ciclo_de_vida.md": "16_multi_agent_composition_and_lifecycle.md",
    }
    pt_index = (PT / "INDEX_DEVELOPER_GUIDE.md").read_text(encoding="utf-8")
    en_index = (ROOT / "docs" / "developer" / "en" / "INDEX_DEVELOPER_GUIDE.md").read_text(encoding="utf-8")
    for pt_name, en_name in pairs.items():
        assert (PT / pt_name).is_file() and pt_name in pt_index
        assert (ROOT / "docs" / "developer" / "en" / en_name).is_file() and en_name in en_index
