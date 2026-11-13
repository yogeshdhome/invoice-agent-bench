"""Mock enterprise AP/ERP services (FastAPI). Same services for both agent arms."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from ..domain.canonical import canonical_json
from ..security.auth import AuthError, Principal, verify_token
from ..security.masking import mask_account
from .db import connect
from .faults import FaultController, LatencyModel
from .repository import NotFound, PreconditionFailed, Repo

MALFORMED = b'{"error": null, "data": {"invoice_id": "INV-'


class HoldIn(BaseModel):
    code: str
    reason: str


class ReasonIn(BaseModel):
    reason: str


class PORefIn(BaseModel):
    po_id: str


class TicketIn(BaseModel):
    invoice_id: str
    summary: str
    assignee_role: str


class VendorPatch(BaseModel):
    bank_account: str | None = None
    name: str | None = None


def _json(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        return [_json(o) for o in obj]
    if isinstance(obj, (Decimal, date)):
        return str(obj)
    return obj


def create_app(db_path: str, faults: FaultController | None = None, latency: LatencyModel | None = None,
               jwt_secret: str | None = None, today: str | None = None) -> FastAPI:
    app = FastAPI(title="Synthetic AP services")
    app.state.faults = faults or FaultController()
    app.state.latency = latency
    app.state.today = today or date.today().isoformat()

    def principal(request: Request) -> Principal:
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            raise HTTPException(401, "missing bearer token")
        try:
            return verify_token(auth[7:], jwt_secret)
        except AuthError as e:
            raise HTTPException(401, f"invalid token: {e}") from e

    def repo(p: Principal = Depends(principal)):
        conn = connect(db_path)
        try:
            yield Repo(conn, p)
        finally:
            conn.close()

    async def guard(tool: str) -> str | None:
        if app.state.latency:
            await app.state.latency.sleep(tool)
        return await app.state.faults.before(tool)

    def out(flag: str | None, payload: Any) -> Response:
        if flag == "malformed":
            return Response(content=MALFORMED, media_type="application/json")
        return JSONResponse(_json(payload))

    def run(fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except NotFound as e:
            raise HTTPException(404, f"not found or not accessible: {e}") from e
        except PreconditionFailed as e:
            raise HTTPException(422, str(e)) from e

    async def write(request: Request, r: Repo, tool: str, target: str, body: dict, fn: Callable[[], dict]) -> Response:
        flag = await guard(tool)
        key = request.headers.get("idempotency-key")
        if not key:
            raise HTTPException(400, "Idempotency-Key header required for writes")
        args_hash = hashlib.sha256(canonical_json({"tool": tool, "target": target, "body": body}).encode()).hexdigest()
        c = r.c
        c.execute("BEGIN IMMEDIATE")
        try:
            row = c.execute("SELECT * FROM action_log WHERE idempotency_key=?", [key]).fetchone()
            if row is not None:
                c.execute("ROLLBACK")
                if row["args_hash"] != args_hash:
                    raise HTTPException(409, "Idempotency-Key reused with different arguments")
                return JSONResponse(json.loads(row["result_json"]), headers={"Idempotent-Replayed": "true"})
            result = run(fn)
            c.execute("INSERT INTO action_log VALUES (?,?,?,?,?,?,?)",
                      [key, tool, target, args_hash, json.dumps(result), r.p.user_id,
                       datetime.now(timezone.utc).isoformat(timespec="seconds")])
            c.execute("COMMIT")
        except Exception:
            if c.in_transaction:
                c.execute("ROLLBACK")
            raise
        return out(flag, result)

    # ---------------- reads ----------------
    @app.get("/invoices/{invoice_id}")
    async def get_invoice(invoice_id: str, r: Repo = Depends(repo)):
        flag = await guard("get_invoice")
        return out(flag, run(lambda: r.get_invoice(invoice_id)))

    @app.get("/invoices")
    async def search_invoices(vendor_id: str | None = None, status: str | None = None, hold_code: str | None = None,
                              vendor_invoice_no: str | None = None, total: str | None = None, date_from: str | None = None,
                              date_to: str | None = None, limit: int = 5, r: Repo = Depends(repo)):
        flag = await guard("search_invoices")
        return out(flag, {"results": r.search_invoices(vendor_id, status, hold_code, vendor_invoice_no, total, date_from, date_to, limit)})

    @app.get("/purchase-orders/{po_id}")
    async def get_po(po_id: str, r: Repo = Depends(repo)):
        flag = await guard("get_purchase_order")
        return out(flag, run(lambda: r.get_po(po_id)))

    @app.get("/purchase-orders/{po_id}/receipts")
    async def get_receipts(po_id: str, r: Repo = Depends(repo)):
        flag = await guard("get_goods_receipts")
        return out(flag, {"po_id": po_id, "receipts": _json(run(lambda: r.get_receipts(po_id)))})

    @app.get("/vendors/{vendor_id}")
    async def get_vendor(vendor_id: str, r: Repo = Depends(repo)):
        flag = await guard("get_vendor")
        v = run(lambda: r.get_vendor(vendor_id))
        d = v.model_dump(mode="json")
        d["bank_account"] = mask_account(d["bank_account"])
        return out(flag, d)

    @app.get("/invoices/{invoice_id}/payments")
    async def get_payments(invoice_id: str, r: Repo = Depends(repo)):
        flag = await guard("get_payment_status")
        return out(flag, {"invoice_id": invoice_id, "payments": _json(run(lambda: r.get_payments(invoice_id)))})

    # ---------------- writes (idempotent) ----------------
    @app.post("/exception-tickets")
    async def create_ticket(body: TicketIn, request: Request, r: Repo = Depends(repo)):
        return await write(request, r, "create_exception_ticket", body.invoice_id, body.model_dump(),
                           lambda: r.create_ticket(body.invoice_id, body.summary, body.assignee_role, r.p.user_id, app.state.today))

    @app.post("/invoices/{invoice_id}/holds")
    async def place_hold(invoice_id: str, body: HoldIn, request: Request, r: Repo = Depends(repo)):
        return await write(request, r, "place_hold", invoice_id, body.model_dump(),
                           lambda: r.place_hold(invoice_id, body.code, body.reason, app.state.today))

    @app.post("/invoices/{invoice_id}/holds/{hold_id}/release")
    async def release_hold(invoice_id: str, hold_id: str, body: ReasonIn, request: Request, r: Repo = Depends(repo)):
        return await write(request, r, "release_hold", f"{invoice_id}/{hold_id}", body.model_dump(),
                           lambda: r.release_hold(invoice_id, hold_id, body.reason, r.p.user_id, app.state.today))

    @app.post("/invoices/{invoice_id}/reject")
    async def reject(invoice_id: str, body: ReasonIn, request: Request, r: Repo = Depends(repo)):
        return await write(request, r, "reject_invoice", invoice_id, body.model_dump(), lambda: r.reject(invoice_id, body.reason))

    @app.post("/invoices/{invoice_id}/po-reference")
    async def po_ref(invoice_id: str, body: PORefIn, request: Request, r: Repo = Depends(repo)):
        return await write(request, r, "update_po_reference", invoice_id, body.model_dump(),
                           lambda: r.update_po_ref(invoice_id, body.po_id))

    @app.post("/invoices/{invoice_id}/approve-payment")
    async def approve(invoice_id: str, request: Request, r: Repo = Depends(repo)):
        return await write(request, r, "approve_for_payment", invoice_id, {}, lambda: r.approve_payment(invoice_id, app.state.today))

    @app.patch("/vendors/{vendor_id}")
    async def update_vendor(vendor_id: str, body: VendorPatch, request: Request, r: Repo = Depends(repo)):
        return await write(request, r, "update_vendor", vendor_id, body.model_dump(),
                           lambda: r.update_vendor(vendor_id, body.model_dump(), app.state.today))

    return app
