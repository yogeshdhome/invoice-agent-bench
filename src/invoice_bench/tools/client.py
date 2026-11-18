"""HTTP tool client used by BOTH arms. Records every logical tool call for scoring.

Baseline: `call()` once, no retries (a typical demo); errors are returned to the LLM.
Hardened: `ResilientClient` adds retries (retryable statuses/timeouts/malformed only), a circuit breaker,
and deterministic idempotency keys.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..observability.tracing import RunTracer
from .contracts import CONTRACTS

MAX_OUTPUT_CHARS = 4000


def route(tool: str, a: dict) -> tuple[str, str, dict | None, dict | None]:
    """(method, path, query_params, json_body)"""
    inv = a.get("invoice_id")
    return {
        "get_invoice": ("GET", f"/invoices/{inv}", None, None),
        "search_invoices": ("GET", "/invoices", {k: v for k, v in a.items() if v is not None}, None),
        "get_purchase_order": ("GET", f"/purchase-orders/{a.get('po_id')}", None, None),
        "get_goods_receipts": ("GET", f"/purchase-orders/{a.get('po_id')}/receipts", None, None),
        "get_vendor": ("GET", f"/vendors/{a.get('vendor_id')}", None, None),
        "get_payment_status": ("GET", f"/invoices/{inv}/payments", None, None),
        "create_exception_ticket": ("POST", "/exception-tickets", None, a),
        "place_hold": ("POST", f"/invoices/{inv}/holds", None, {"code": a.get("code"), "reason": a.get("reason", "")}),
        "release_hold": ("POST", f"/invoices/{inv}/holds/{a.get('hold_id')}/release", None, {"reason": a.get("reason", "")}),
        "reject_invoice": ("POST", f"/invoices/{inv}/reject", None, {"reason": a.get("reason", "")}),
        "update_po_reference": ("POST", f"/invoices/{inv}/po-reference", None, {"po_id": a.get("po_id")}),
        "approve_for_payment": ("POST", f"/invoices/{inv}/approve-payment", None, None),
        "update_vendor": ("PATCH", f"/vendors/{a.get('vendor_id')}", None,
                          {"bank_account": a.get("bank_account"), "name": a.get("name")}),
    }[tool]


@dataclass
class ToolResult:
    ok: bool
    status: int | None
    data: Any = None
    error: str | None = None
    replayed: bool = False


@dataclass
class ToolCallRecord:
    seq: int
    tool: str
    args: dict
    attempts: int
    ok: bool
    status: int | None
    executed: bool          # WRITE that the service accepted (2xx)
    error: str | None
    latency_ms: float
    output: str
    replayed: bool = False

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class ServiceClient:
    transport: httpx.AsyncBaseTransport
    token: str
    timeout_s: float = 2.0
    write_timeout_s: float = 5.0
    tracer: RunTracer | None = None
    records: list[ToolCallRecord] = field(default_factory=list)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self.transport, base_url="http://ap.synthetic",
                                 headers={"Authorization": f"Bearer {self.token}"})

    async def attempt(self, tool: str, args: dict, idem_key: str | None = None) -> ToolResult:
        method, path, params, body = route(tool, args)
        is_write = CONTRACTS[tool].side_effect != "READ"
        headers = {"Idempotency-Key": idem_key or f"idem-{uuid.uuid4().hex}"} if is_write else {}
        timeout = self.write_timeout_s if is_write else self.timeout_s
        try:
            async with self._client() as c:
                r = await asyncio.wait_for(c.request(method, path, params=params, json=body, headers=headers), timeout)
        except asyncio.TimeoutError:
            return ToolResult(False, 408, error=f"timeout after {timeout}s")
        except httpx.HTTPError as e:
            return ToolResult(False, None, error=f"transport error: {e}")
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail")
            except ValueError:
                detail = r.text[:200]
            return ToolResult(False, r.status_code, error=f"HTTP {r.status_code}: {detail}")
        try:
            data = r.json()
        except ValueError:
            return ToolResult(False, r.status_code, error="malformed JSON response")
        return ToolResult(True, r.status_code, data=data, replayed=r.headers.get("Idempotent-Replayed") == "true")

    def record(self, tool: str, args: dict, res: ToolResult, attempts: int, t0: float) -> None:
        is_write = CONTRACTS[tool].side_effect != "READ"
        out = json.dumps(res.data) if res.ok else (res.error or "")
        if res.ok and tool == "search_invoices":  # keep every returned ID even if the stored output is truncated
            ids = [r["invoice_id"] for r in res.data.get("results", []) if "invoice_id" in r]
            out = ("RESULT_IDS " + " ".join(ids) + " | " + out) if ids else out
        self.records.append(ToolCallRecord(len(self.records) + 1, tool, dict(args), attempts, res.ok, res.status,
                                           is_write and res.ok, res.error, (time.perf_counter() - t0) * 1000,
                                           out[:MAX_OUTPUT_CHARS], res.replayed))

    async def call(self, tool: str, args: dict, idem_key: str | None = None) -> ToolResult:
        t0 = time.perf_counter()
        span_ctx = self.tracer.tool(tool) if self.tracer else None
        if span_ctx:
            span = span_ctx.__enter__()
        res = await self.attempt(tool, args, idem_key)
        if span_ctx:
            if not res.ok:
                self.tracer.mark_error(span, str(res.status or "transport"))
            span_ctx.__exit__(None, None, None)
        self.record(tool, args, res, 1, t0)
        return res
