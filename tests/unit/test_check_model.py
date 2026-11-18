from invoice_bench.bench import check_model as cm


class _Resp:
    def __init__(self, data): self._d = data
    def raise_for_status(self): pass
    def json(self): return self._d


def _cfg(**kw):
    c = {"model": "anthropic/claude-haiku-5.5", "temperature": 0, "structured_output_method": "json_schema",
         "openrouter_provider": {"order": ["anthropic"], "allow_fallbacks": False, "require_parameters": True}}
    c.update(kw)
    return c


def _eps(params):
    return {"data": {"endpoints": [{"provider_name": "Anthropic", "tag": "anthropic", "status": 0, "supported_parameters": params},
                                   {"provider_name": "Google Vertex", "tag": "google-vertex", "supported_parameters": []}]}}


def test_detects_unsupported_temperature(monkeypatch):
    monkeypatch.setattr(cm.httpx, "get", lambda *a, **k: _Resp(_eps(["max_tokens", "tools", "tool_choice", "response_format"])))
    ok, rep = cm.endpoint_report(_cfg())
    pinned = next(r for r in rep["endpoints"] if r.get("pinned"))
    assert not ok and pinned["missing_for_our_calls"]["baseline_agent_step"] == ["temperature"]
    ok2, _ = cm.endpoint_report(_cfg(temperature=None))
    assert ok2  # unpinned endpoints (Vertex) are ignored


def test_function_calling_method_requires_tool_choice(monkeypatch):
    monkeypatch.setattr(cm.httpx, "get", lambda *a, **k: _Resp(_eps(["max_tokens", "temperature", "tools", "response_format"])))
    assert cm.endpoint_report(_cfg())[0]
    ok, rep = cm.endpoint_report(_cfg(structured_output_method="function_calling"))
    assert not ok


def test_request_params_match_captured_requests():
    p = cm.request_params(_cfg())
    assert p["baseline_agent_step"] == {"max_tokens", "temperature", "tools"}
    assert p["hardened_intent"] == {"max_tokens", "temperature", "response_format"}


def test_reasoning_param_is_checked_when_configured(monkeypatch):
    monkeypatch.setattr(cm.httpx, "get", lambda *a, **k: _Resp(_eps(["max_tokens", "tools", "response_format"])))
    ok, rep = cm.endpoint_report(_cfg(temperature=None, reasoning={"enabled": False}))
    pinned = next(r for r in rep["endpoints"] if r.get("pinned"))
    assert not ok and "reasoning" in pinned["missing_for_our_calls"]["hardened_explainer"]


def test_fail_line_names_missing_parameter(monkeypatch, capsys):
    import pytest
    monkeypatch.setattr(cm.httpx, "get", lambda *a, **k: _Resp(_eps(["max_tokens", "tools", "response_format"])))
    monkeypatch.setattr(cm, "load_model_cfg", lambda: _cfg())
    monkeypatch.setattr("sys.argv", ["check_model", "--no-calls"])
    with pytest.raises(SystemExit):
        cm.main()
    err = capsys.readouterr().err
    assert "do not support: ['temperature']" in err and "supported_by_pinned" in err
