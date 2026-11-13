"""OpenRouter wiring (offline: no request is sent)."""
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from invoice_bench.llm.factory import get_chat_model, load_model_cfg
from invoice_bench.llm.usage import BudgetCallback


def test_factory_builds_pinned_openrouter_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-dummy")
    cfg = load_model_cfg()
    m = get_chat_model(cfg)
    assert type(m).__name__ == "ChatOpenRouter" and m.model_name == "anthropic/claude-haiku-5.5"
    p = m._default_params
    assert p["provider"] == {"order": ["anthropic"], "allow_fallbacks": False, "require_parameters": True}
    assert "temperature" not in p and p["max_tokens"] == 800        # endpoint rejects temperature (p2 check)
    assert p["reasoning"] == {"effort": "none"}


def test_usage_callback_records_cost_and_served_provider():
    cb = BudgetCallback(5, 10_000)
    msg = AIMessage(content="ok", usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120,
                                                  "output_token_details": {"reasoning": 7}},
                    response_metadata={"cost": 0.00002, "provider": "Anthropic"})
    import uuid
    rid = uuid.uuid4()
    cb.on_chat_model_start({}, [[]], run_id=rid)
    cb.on_llm_end(LLMResult(generations=[[ChatGeneration(message=msg)]]), run_id=rid)
    u = cb.usage
    assert (u.input_tokens, u.output_tokens, u.reasoning_tokens, u.cost_reported_calls) == (100, 20, 7, 1)
    assert abs(u.cost - 0.00002) < 1e-12 and u.served_providers == {"Anthropic": 1}
