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
def documented_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    for name in tuple(sys.modules):
        if name == "financial_agent" or name.startswith("financial_agent."):
            sys.modules.pop(name, None)
    package = tmp_path / "financial_agent" / "extensions"
    package.mkdir(parents=True)
    prompts = package / "prompts"
    prompts.mkdir()
    (tmp_path / "financial_agent" / "__init__.py").write_text("", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (prompts / "__init__.py").write_text("", encoding="utf-8")
    (prompts / "financial_policy.py").write_text(_block("external-guardrail-prompt-example"), encoding="utf-8")
    (package / "guardrails.py").write_text(_block("external-guardrail-example"), encoding="utf-8")
    (package / "llm_guardrails.py").write_text(_block("external-llm-guardrail-example"), encoding="utf-8")
    (package / "judges.py").write_text(_block("external-judge-example"), encoding="utf-8")
    (tmp_path / "guardrails.yaml").write_text(_block("external-guardrail-yaml"), encoding="utf-8")
    (tmp_path / "judges.yaml").write_text(_block("external-judge-yaml"), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    for name in tuple(sys.modules):
        if name == "financial_agent" or name.startswith("financial_agent."):
            sys.modules.pop(name, None)


class FakeGuardrailLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[list[dict[str, str]], dict]] = []

    async def ainvoke(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.response


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
async def test_documented_llm_guardrail_uses_agent_prompt_and_shared_llm(documented_agent: Path) -> None:
    from financial_agent.extensions.llm_guardrails import FinancialPolicyLLMRail

    llm = FakeGuardrailLLM('{"allowed": false, "reason": "Operação fora da política."}')
    pipeline = GuardrailPipeline(tool_rails=[FinancialPolicyLLMRail()], llm=llm)
    _, decisions = await pipeline.run_tool("transfer", {"amount": 2000.0})

    assert not decisions[0].allowed
    assert decisions[0].metadata["prompt_version"] == "financial-policy-v1"
    messages, kwargs = llm.calls[0]
    assert "classificador de política financeira" in messages[0]["content"]
    assert kwargs["profile_name"] == "guardrail"


@pytest.mark.asyncio
async def test_documented_llm_guardrail_fails_closed_without_llm(documented_agent: Path) -> None:
    from financial_agent.extensions.llm_guardrails import FinancialPolicyLLMRail

    decision = await FinancialPolicyLLMRail().evaluate("transfer", {"tool_name": "transfer"})
    assert not decision.allowed
    assert "não foi disponibilizado" in decision.reason


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
