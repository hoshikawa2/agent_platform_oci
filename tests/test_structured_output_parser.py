import pytest

from agent_framework.llm.structured_output import (
    StructuredOutputError,
    parse_json_object,
    parse_structured_output,
)


def test_strict_json_object():
    assert parse_json_object('{"decision":"KEEP","confidence":0.9}') == {
        "decision": "KEEP",
        "confidence": 0.9,
    }


def test_single_quotes_python_literal():
    assert parse_json_object("{'decision': 'KEEP', 'confidence': 0.9, 'ok': True, 'reason': None}") == {
        "decision": "KEEP",
        "confidence": 0.9,
        "ok": True,
        "reason": None,
    }


def test_prose_around_json():
    raw = 'Resultado da análise:\n{"decision":"ROUTE","confidence":0.8}\nFim.'
    assert parse_json_object(raw)["decision"] == "ROUTE"


def test_prose_around_single_quoted_mapping():
    raw = "Vou retornar o objeto pedido: {'decision': 'HANDOFF', 'confidence': 0.7} texto final"
    assert parse_json_object(raw)["decision"] == "HANDOFF"


def test_markdown_fence():
    raw = "```json\n{\"allowed\": true, \"reason\": \"OK\"}\n```"
    assert parse_json_object(raw) == {"allowed": True, "reason": "OK"}


def test_braces_inside_string_do_not_break_extraction():
    raw = "prefix {'reason': 'cliente disse {nao}', 'allowed': True} suffix"
    assert parse_json_object(raw)["reason"] == "cliente disse {nao}"


def test_apostrophe_inside_double_quoted_json_is_preserved():
    raw = 'texto {"name":"D\'Ávila","allowed":true} fim'
    assert parse_json_object(raw)["name"] == "D'Ávila"


def test_array_supported_by_generic_parser():
    assert parse_structured_output("prefix [1, 2, 3] suffix", expected_type=list) == [1, 2, 3]


def test_object_wrapper_rejects_array():
    with pytest.raises(StructuredOutputError):
        parse_json_object("[1,2,3]")


def test_does_not_execute_arbitrary_python():
    with pytest.raises(StructuredOutputError):
        parse_json_object("{'x': __import__('os').system('echo unsafe')}")
