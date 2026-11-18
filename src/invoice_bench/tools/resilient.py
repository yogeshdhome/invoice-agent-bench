"""Hardened tool execution: bounded retries only where safe, circuit breaker, deterministic idempotency."""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field

from .client import ServiceClient, ToolResult
from .contracts import CONTRACTS

MALFORMED_STATUS = -1


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    backoff_initial_s: float = 0.2
    backoff_max_s: float = 2.0
    retryable_statuses: tuple[int, ...] = (408, 429, 503, 504)
    breaker_threshold: int = 5
    breaker_reset_s: float = 30.0


@dataclass
class ResilientClient:
    inner: ServiceClient
    policy: RetryPolicy = field(default_factory=RetryPolicy)
    rng: random.Random = field(default_factory=lambda: random.Random(0))
    sleep: callable = asyncio.sleep
    _failures: dict[str, int] = field(default_factory=dict)
    _opened_at: dict[str, float] = field(default_factory=dict)

    def _retryable(self, tool: str, res: ToolResult) -> bool:
        c = CONTRACTS[tool]
        if c.side_effect != "READ" and not c.idempotent:
            return False  # never retry a non-idempotent write
        return res.status in self.policy.retryable_statuses or res.error == "malformed JSON response" or res.status is None

    async def call(self, tool: str, args: dict, idem_key: str | None = None) -> ToolResult:
        if CONTRACTS[tool].side_effect != "READ" and not idem_key:
            raise ValueError("hardened writes require a deterministic idempotency key")
        opened = self._opened_at.get(tool)
        if opened and time.monotonic() - opened < self.policy.breaker_reset_s:
            res = ToolResult(False, 503, error="circuit open")
            self.inner.record(tool, args, res, 0, time.perf_counter())
            return res
        t0, attempt, res = time.perf_counter(), 0, None
        span_ctx = self.inner.tracer.tool(tool) if self.inner.tracer else None
        span = span_ctx.__enter__() if span_ctx else None
        while attempt < self.policy.max_attempts:
            attempt += 1
            res = await self.inner.attempt(tool, args, idem_key)
            if res.ok or not self._retryable(tool, res):
                break
            if attempt < self.policy.max_attempts:
                delay = min(self.policy.backoff_max_s, self.policy.backoff_initial_s * 2 ** (attempt - 1))
                await self.sleep(delay * (0.5 + self.rng.random() / 2))  # jittered exponential backoff
        if res.ok:
            self._failures[tool] = 0
            self._opened_at.pop(tool, None)
        else:
            self._failures[tool] = self._failures.get(tool, 0) + 1
            if self._failures[tool] >= self.policy.breaker_threshold:
                self._opened_at[tool] = time.monotonic()
            if span:
                self.inner.tracer.mark_error(span, str(res.status or "transport"))
        if span_ctx:
            span_ctx.__exit__(None, None, None)
        self.inner.record(tool, args, res, attempt, t0)
        return res
