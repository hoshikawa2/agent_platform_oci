from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "EXTERNAL_GUARDRAILS_JUDGES.md"
FRAMEWORK_SRC = ROOT / "libs" / "agent_framework" / "src"
if str(FRAMEWORK_SRC) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_SRC))

from agent_framework.guardrails.pipeline import GuardrailPipeline
from agent_framework.judges.judge import JudgePipeline


def _block(tag: str) -> str:
    text = GUIDE.read_text(encoding="utf-8")
    match = re.search(rf"```(?:python|yaml) {re.escape(tag)}\n(.*?)```", text, re.DOTALL)
    assert match, f"bloco {tag!r} ausente do manual"
    return match.group(1)


@pytest.fixture()
def documented_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    package = tmp_path / "financial_agent" / "extensions"
    package.mkdir(parents=True)
    (tmp_path / "financial_agent" / "__init__.py").write_text("", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "guardrails.py").write_text(_block("external-guardrail-example"), encoding="utf-8")
    (package / "judges.py").write_text(_block("external-judge-example"), encoding="utf-8")
    (tmp_path / "guardrails.yaml").write_text(_block("external-guardrail-yaml"), encoding="utf-8")
    (tmp_path / "judges.yaml").write_text(_block("external-judge-yaml"), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    return tmp_path


@pytest.mark.asyncio
async def test_documented_external_guardrail_loads_and_enforces_policy(documented_agent: Path) -> None:
    pipeline = GuardrailPipeline(config_path=str(documented_agent / "guardrails.yaml"))

    _, allowed = await pipeline.run_tool("transfer", {"amount": 1200.0})
    _, denied = await pipeline.run_tool("transfer", {"amount": 2000.0})
    _, missing = await pipeline.run_tool("transfer", {})

    assert allowed[0].code == "FIN_AMOUNT" and allowed[0].allowed
    assert denied[0].code == "FIN_AMOUNT" and not denied[0].allowed
    assert missing[0].code == "FIN_AMOUNT" and not missing[0].allowed


@pytest.mark.asyncio
async def test_documented_external_judge_loads_with_injection(documented_agent: Path) -> None:
    fake_llm = object()
    settings = SimpleNamespace(ENABLE_JUDGES=True)
    pipeline = JudgePipeline(
        llm=fake_llm,
        settings=settings,
        config_path=str(documented_agent / "judges.yaml"),
    )

    passed = await pipeline.evaluate_all("Qual foi o saldo?", "O saldo foi R$ 100.", {"evidence": "R$ 100"})
    failed = await pipeline.evaluate_all("Qual foi o saldo?", "Não tenho dados.", {"evidence": "R$ 100"})

    assert pipeline.judges[0].llm is fake_llm
    assert passed[0].name == "financial_evidence" and passed[0].passed
    assert failed[0].name == "financial_evidence" and not failed[0].passed
