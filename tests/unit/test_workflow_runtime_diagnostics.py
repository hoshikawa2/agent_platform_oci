from agent_framework.workflows.runtime import _exception_details, _type_shape


def _boom():
    raise AttributeError("'str' object has no attribute 'override'")


def test_exception_details_contains_traceback():
    try:
        _boom()
    except Exception as exc:
        details = _exception_details(exc, runtime_context={"phase": "ainvoke"})
    assert details["type"] == "AttributeError"
    assert "_boom" in details["traceback"]
    assert "override" in details["traceback"]
    assert details["runtime_diagnostics"]["phase"] == "ainvoke"


def test_type_shape_exposes_types_not_values():
    shape = _type_shape({"configurable": {"thread_id": "secret-thread", "__pregel_runtime": "bad-runtime"}})
    text = repr(shape)
    assert "thread_id" in text
    assert "__pregel_runtime" in text
    assert "secret-thread" not in text
    assert "bad-runtime" not in text
    assert "str" in text
