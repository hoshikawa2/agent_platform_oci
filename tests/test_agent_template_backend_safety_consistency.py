from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _template_dirs():
    return sorted(
        p
        for p in ROOT.rglob("*")
        if p.is_dir() and p.name in {"agent_template_backend", "agent_template_backend_day_zero"}
    )


def test_all_agent_template_backend_copies_have_safe_agent_prompts():
    targets = _template_dirs()
    assert targets, "Nenhum template backend encontrado"
    for base in targets:
        checks = {
            "billing_agent.py": (
                "Nunca exponha identificadores técnicos",
                "Não acrescente canais",
                "Se uma tool retornar BLOCKED",
            ),
            "product_agent.py": (
                "Nunca exponha identificadores técnicos",
                "can.cancel",
                "Se uma tool retornar BLOCKED",
            ),
            "orders_agent.py": (
                "Nunca exponha identificadores técnicos",
                "Não declare sucesso",
                "Se uma tool retornar BLOCKED",
            ),
            "support_agent.py": (
                "Nunca exponha identificadores técnicos",
                "Não declare sucesso",
                "Se uma tool retornar BLOCKED",
            ),
        }
        for filename, required in checks.items():
            text = (base / "app" / "agents" / filename).read_text(encoding="utf-8")
            for marker in required:
                assert marker in text, f"{base.relative_to(ROOT)}/{filename} sem {marker!r}"


def test_all_agent_template_backend_copies_isolate_interrupted_transaction_context():
    for base in _template_dirs():
        graph = (base / "app" / "workflows" / "agent_graph.py").read_text(encoding="utf-8")
        assert 'route_metadata.get("transaction_interruption")' in graph
        assert '== "intent_shift"' in graph
        assert 'ctx["historical_transaction_ignored"] = True' in graph
        assert 'ctx["expected_protocols"] = protocols' in graph
        assert 'self._output_guardrail_context(state)' in graph


def test_full_templates_do_not_dump_raw_invoice_payload():
    checked = 0
    for base in _template_dirs():
        renderer = base / "app" / "presentation" / "tool_renderers.py"
        if not renderer.exists():
            continue
        checked += 1
        text = renderer.read_text(encoding="utf-8")
        assert 'Fatura consultada: {result}' not in text
        assert 'result.get("valor_total")' in text
        assert 'result.get("vencimento")' in text
        assert 'result.get("status")' in text
        assert 'result.get("itens")' in text
    assert checked > 0
