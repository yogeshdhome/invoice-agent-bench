"""Seeded, declarative fault and latency injection for mock services (B8, NFR-06)."""
from __future__ import annotations

import asyncio
import math
import random
from dataclasses import dataclass, field
from typing import Literal

from fastapi import HTTPException

FaultType = Literal["timeout", "http_429", "http_500", "http_503", "malformed"]
_STATUS = {"http_429": 429, "http_500": 500, "http_503": 503}


@dataclass
class FaultSpec:
    tool: str
    fault: FaultType
    times: int | Literal["always"] = 1
    delay_s: float = 5.0  # for timeouts; must exceed the client timeout


@dataclass
class FaultController:
    plan: list[FaultSpec] = field(default_factory=list)
    _fired: dict[int, int] = field(default_factory=dict)

    def reset(self, plan: list[FaultSpec] | list[dict] | None = None) -> None:
        self.plan = [p if isinstance(p, FaultSpec) else FaultSpec(**p) for p in (plan or [])]
        self._fired = {}

    async def before(self, tool: str) -> str | None:
        """Apply the first still-active fault for `tool`. Returns 'malformed' if the body must be corrupted."""
        for i, spec in enumerate(self.plan):
            if spec.tool != tool:
                continue
            n = self._fired.get(i, 0)
            if spec.times != "always" and n >= spec.times:
                continue
            self._fired[i] = n + 1
            if spec.fault == "timeout":
                await asyncio.sleep(spec.delay_s)
                return None
            if spec.fault == "malformed":
                return "malformed"
            raise HTTPException(status_code=_STATUS[spec.fault], detail=f"injected {spec.fault}")
        return None


class LatencyModel:
    def __init__(self, profile: dict, seed: int):
        self.profile = profile
        self.rng = random.Random(seed)

    async def sleep(self, tool: str) -> None:
        spec = self.profile.get(tool) or self.profile.get("default_write") or {"median_ms": 100, "sigma": 0.3}
        ms = math.exp(math.log(spec["median_ms"]) + spec["sigma"] * self.rng.gauss(0, 1))
        await asyncio.sleep(ms / 1000)
