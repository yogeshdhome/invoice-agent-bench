"""Ablation A1: baseline + on-behalf-of identity + policy DENY at the tool boundary. No workflow, no approval gate
(approval stays conversational, as in the baseline)."""
from __future__ import annotations

import time
from dataclasses import dataclass

from ..security.auth import Principal
from ..security.policy import Effect, PolicyEngine, ResourceContext
from .client import ServiceClient, ToolResult
from .contracts import CONTRACTS


@dataclass
class PolicyGuardClient:
    inner: ServiceClient
    policy: PolicyEngine
    principal: Principal

    @property
    def records(self):
        return self.inner.records

    async def call(self, tool: str, args: dict, idem_key: str | None = None) -> ToolResult:
        res_ctx = None
        if CONTRACTS[tool].side_effect != "READ" and args.get("invoice_id"):
            r = await self.inner.attempt("get_invoice", {"invoice_id": args["invoice_id"]})  # context lookup, not a model call
            if r.ok:
                res_ctx = ResourceContext(tenant_id=r.data["tenant_id"], bu_id=r.data["bu_id"], active_hold_count=len(r.data["holds"]))
        if CONTRACTS[tool].side_effect != "READ":
            d = self.policy.decide(self.principal, tool, res_ctx)
            if d.effect == Effect.DENY:
                res = ToolResult(False, 403, error=f"denied by policy {d.rule_id}: {d.reason}")
                self.inner.record(tool, args, res, 0, time.perf_counter())
                return res
        return await self.inner.call(tool, args, idem_key)
