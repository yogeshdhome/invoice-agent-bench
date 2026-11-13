"""Usage accounting + per-run budgets via a LangChain callback (applied identically to both arms)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler


class BudgetExceeded(Exception):
    pass


@dataclass
class Usage:
    llm_calls: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cost: float = 0.0                       # provider-reported cost (OpenRouter credits = USD); 0 if not reported
    cost_reported_calls: int = 0
    served_providers: dict = field(default_factory=dict)   # upstream provider -> call count
    llm_ms: float = 0.0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


class BudgetCallback(BaseCallbackHandler):
    """Counts LLM calls/tokens and enforces per-run and global budgets. Raises (raise_error=True) to stop a run."""

    raise_error = True

    def __init__(self, max_llm_calls: int, max_input_tokens_per_run: int, global_remaining: list[int] | None = None,
                 tracer: Any = None):
        self.max_llm_calls, self.max_input_tokens_per_run = max_llm_calls, max_input_tokens_per_run
        self.global_remaining, self.tracer = global_remaining, tracer
        self.usage = Usage()
        self._starts: dict = {}

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        if self.usage.llm_calls >= self.max_llm_calls:
            raise BudgetExceeded(f"max_llm_calls={self.max_llm_calls}")
        if self.global_remaining is not None and self.global_remaining[0] <= 0:
            raise BudgetExceeded("global token budget exhausted")
        self._starts[run_id] = time.perf_counter()

    def on_llm_end(self, response, *, run_id, **kwargs):
        self.usage.llm_calls += 1
        self.usage.llm_ms += (time.perf_counter() - self._starts.pop(run_id, time.perf_counter())) * 1000
        for gen in response.generations:
            for g in gen:
                msg = getattr(g, "message", None)
                um = getattr(msg, "usage_metadata", None) or {}
                rm = getattr(msg, "response_metadata", None) or {}
                if isinstance(rm.get("cost"), (int, float)):
                    self.usage.cost += float(rm["cost"])
                    self.usage.cost_reported_calls += 1
                prov = rm.get("provider") or "unreported"  # NOT model_provider: that is just "openrouter"
                self.usage.served_providers[prov] = self.usage.served_providers.get(prov, 0) + 1
                self.usage.reasoning_tokens += int((um.get("output_token_details") or {}).get("reasoning", 0) or 0)
                it, ot = int(um.get("input_tokens", 0)), int(um.get("output_tokens", 0))
                cached = int((um.get("input_token_details") or {}).get("cache_read", 0) or 0)
                self.usage.input_tokens += it
                self.usage.output_tokens += ot
                self.usage.cached_input_tokens += cached
                if self.global_remaining is not None:
                    self.global_remaining[0] -= it + ot
                if self.tracer:
                    self.tracer.chat_span(it, ot, cached)
        if self.usage.input_tokens > self.max_input_tokens_per_run:
            raise BudgetExceeded(f"max_input_tokens_per_run={self.max_input_tokens_per_run}")
