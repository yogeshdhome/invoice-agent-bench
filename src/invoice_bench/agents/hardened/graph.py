"""Hardened arm (H): LLM proposes, code disposes.

LLM is used for (1) intent/entity extraction and (2) evidence-constrained explanation. Everything else -
evidence gathering, status, next action, authorisation, approval binding, idempotent execution - is code.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Callable, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from ...domain.canonical import action_hash, canonical_json, idempotency_key
from ...domain.models import (PRE_PAYMENT_STATUSES, GoodsReceipt, HoldCode, Invoice, InvoiceStatus, Payment, PurchaseOrder,
                              Vendor)
from ...domain.next_action import recommend
from ...domain.rules import Tolerance, evaluate_invoice
from ...observability.audit import AuditLog
from ...security.auth import Principal
from ...security.policy import Effect, PolicyEngine, ResourceContext
from ...security.untrusted import delimit
from ...tools.resilient import ResilientClient
from .grounding import corpus, unsupported
from .prompts import ACTION_NOTE, COMPOSE_SYSTEM, INTENT_SYSTEM, Intent

INV_RE = re.compile(r"\bINV[-\s]?(\d{5})\b", re.I)
SYSTEM_NAMES = {"get_invoice": "invoice service", "get_purchase_order": "purchase-order service",
                "get_goods_receipts": "goods-receipt service", "get_vendor": "vendor service",
                "get_payment_status": "payment service", "search_invoices": "invoice search"}


class HState(TypedDict, total=False):
    new_turn: str
    user_turns: list[str]
    session_invoices: list[str]
    intent: dict
    targets: list[str]
    clarify: str | None
    evidence: dict
    answer: str
    grounding_attempts: int
    grounding_feedback: list[str]
    proposed_action: dict | None
    approval: dict | None
    action_message: str | None
    action_result: dict | None
    final: str
    outcome: str


@dataclass
class HardenedDeps:
    model: Any
    client: ResilientClient
    policy: PolicyEngine
    directory: dict[str, Principal]
    audit: AuditLog
    tolerance: Tolerance = field(default_factory=Tolerance)
    approval_ttl_s: int = 3600
    clock: Callable[[], float] = time.time
    crash_hook: Callable[[str], None] | None = None
    structured_kwargs: dict = field(default_factory=dict)   # e.g. {"method": "json_schema"}


def _principal(config) -> Principal:
    return Principal(**config["configurable"]["principal"])


def _run_id(config) -> str:
    return config["configurable"].get("bench_run_id", "run")


def build_hardened(deps: HardenedDeps, checkpointer):
    D = deps

    def audit(config, event, rule_id=None, **kw):
        D.audit.log(_run_id(config), _principal(config).user_id, event, rule_id, **kw)

    # ------------------------------------------------------------------ nodes
    async def ingest(state: HState, config):
        turns = list(state.get("user_turns", [])) + [state["new_turn"]]
        audit(config, "request_received", turn=len(turns))
        return {"user_turns": turns, "clarify": None, "proposed_action": None, "approval": None, "action_message": None,
                "action_result": None, "grounding_attempts": 0, "grounding_feedback": [], "evidence": {}, "targets": []}

    async def classify_intent(state: HState, config):
        # Planning context = the user's own words + IDs we resolved earlier. No tool output (context minimisation).
        payload = {"turns": state["user_turns"], "previously_discussed_invoices": state.get("session_invoices", [])}
        r = await D.model.with_structured_output(Intent, include_raw=True, **D.structured_kwargs).ainvoke(
            [SystemMessage(INTENT_SYSTEM), HumanMessage(json.dumps(payload))], config=config)
        intent = r["parsed"] or Intent(intent="other")
        audit(config, "intent_classified", intent=intent.intent, action=intent.requested_action)
        return {"intent": intent.model_dump()}

    async def resolve_targets(state: HState, config):
        it = Intent(**state["intent"])
        last = state["user_turns"][-1]
        ids = []
        # tune_t1 (AP-003): "Reject INV-A, it's a duplicate of INV-B" was forced into a clarify because a regex scan added
        # INV-B as a second target. Targets now come from the model's extraction; the regex is only a fallback.
        related = {f"INV-{m.group(1)}" for r in it.related_invoice_ids if (m := INV_RE.search(r))}
        scanned = [f"INV-{m}" for m in INV_RE.findall(last) if f"INV-{m}" not in related]
        for raw in (it.invoice_ids or scanned):
            m = INV_RE.search(raw)
            if m and (n := f"INV-{m.group(1)}") not in ids:
                ids.append(n)
        if it.intent == "open_ended":
            return {"targets": []}
        if not ids and it.vendor_invoice_no:
            res = await D.client.call("search_invoices", {"vendor_invoice_no": it.vendor_invoice_no, "limit": 5})
            hits = [x["invoice_id"] for x in (res.data or {}).get("results", []) if "invoice_id" in x] if res.ok else []
            if len(hits) == 1:
                ids = hits
            elif len(hits) > 1:
                return {"clarify": f"More than one invoice matches vendor invoice number {it.vendor_invoice_no}: "
                                   f"{', '.join(hits)}. Which one do you mean?"}
            else:
                return {"clarify": f"I couldn't find an invoice with vendor invoice number {it.vendor_invoice_no} in your scope. "
                                   "Could you share the invoice ID (e.g. INV-12345)?"}
        if not ids:
            prev = state.get("session_invoices", [])
            if len(prev) == 1:
                ids = prev
            elif len(prev) > 1:
                return {"clarify": f"Which invoice do you mean: {' or '.join(prev)}?"}
            else:
                return {"clarify": "Which invoice are you referring to? Please share the invoice ID (e.g. INV-12345)."}
        if it.requested_action != "none" and len(ids) > 1:
            return {"clarify": f"Which invoice should I act on: {' or '.join(ids)}?"}
        return {"targets": ids[:2]}

    async def gather_evidence(state: HState, config):
        it = Intent(**state["intent"])
        pr = _principal(config)
        ev: dict = {"invoices": {}, "unavailable": [], "not_accessible": []}
        call = D.client.call

        def fail(tool, res):
            if res.status != 404:
                ev["unavailable"].append(SYSTEM_NAMES.get(tool, tool))

        if it.intent == "open_ended":
            filt = {"vendor_id": it.vendor_id, "hold_code": it.hold_code,
                    "status": it.status_filter or ("ON_HOLD" if it.hold_code else None), "limit": 20}
            res = await call("search_invoices", {k: v for k, v in filt.items() if v is not None})
            if not res.ok:
                fail("search_invoices", res)
                return {"evidence": ev}
            rows = [x for x in res.data["results"] if "invoice_id" in x][:10]
            out = []
            for row in rows:
                r = await call("get_invoice", {"invoice_id": row["invoice_id"]})
                holds = [h["code"] for h in r.data.get("holds", [])] if r.ok else ["(unavailable)"]
                nxt = recommend(InvoiceStatus(row["status"]), [HoldCode(c) for c in holds if c in HoldCode.__members__]) if r.ok else []
                out.append({"invoice_id": row["invoice_id"], "status": row["status"], "total": row["total"],
                            "currency": row["currency"], "vendor_id": row["vendor_id"], "active_holds": holds,
                            "next_action": nxt[0].as_dict() | {"description": nxt[0].description} if nxt else None})
            held = [x for x in out if x["active_holds"]]
            by_code: dict[str, int] = {}
            for x in held:
                for c in x["active_holds"]:
                    by_code[c] = by_code.get(c, 0) + 1
            ev["search"] = {"filters": filt, "results": out, "truncated": any("truncated" in x for x in res.data["results"]),
                            "aggregates": {"count": len(out), "on_hold_count": len(held), "by_hold_code": by_code,
                                           "total_on_hold": str(sum((Decimal(x["total"]) for x in held), Decimal("0")))}}
            return {"evidence": ev}

        for iid in state["targets"]:
            r = await call("get_invoice", {"invoice_id": iid})
            if not r.ok:
                (ev["not_accessible"].append(iid) if r.status == 404 else fail("get_invoice", r))
                continue
            inv = r.data
            # Defence in depth: re-check scope even though the service already scoped the read.
            d = D.policy.in_scope(pr, ResourceContext(tenant_id=inv["tenant_id"], bu_id=inv["bu_id"]))
            if d is not None:
                audit(config, "scope_violation_blocked", d.rule_id, invoice_id=iid)
                ev["not_accessible"].append(iid)
                continue
            e: dict = {"invoice": inv, "po": None, "receipts": [], "vendor": None, "payments": [], "vendor_invoices": [],
                       "po_lookup": "none"}
            if inv.get("po_ref"):
                p = await call("get_purchase_order", {"po_id": inv["po_ref"]})
                if p.ok:
                    e["po"], e["po_lookup"] = p.data, "found"
                    g = await call("get_goods_receipts", {"po_id": inv["po_ref"]})
                    e["receipts"] = g.data["receipts"] if g.ok else None
                    if not g.ok:
                        fail("get_goods_receipts", g)
                else:
                    e["po_lookup"] = "not_found" if p.status == 404 else "unavailable"
                    fail("get_purchase_order", p)
            v = await call("get_vendor", {"vendor_id": inv["vendor_id"]})
            e["vendor"] = v.data if v.ok else None
            if not v.ok:
                fail("get_vendor", v)
            pay = await call("get_payment_status", {"invoice_id": iid})
            e["payments"] = pay.data["payments"] if pay.ok else None
            if not pay.ok:
                fail("get_payment_status", pay)
            if inv["status"] in [s.value for s in PRE_PAYMENT_STATUSES]:
                s = await call("search_invoices", {"vendor_id": inv["vendor_id"], "limit": 20})
                e["vendor_invoices"] = [x for x in s.data["results"] if "invoice_id" in x] if s.ok else None
            ev["invoices"][iid] = e
        return {"evidence": ev}

    async def evaluate(state: HState, config):
        ev = dict(state["evidence"])
        for iid, e in ev.get("invoices", {}).items():
            inv = Invoice.model_validate(e["invoice"])
            stored = [str(c) for c in inv.active_hold_codes]
            po = PurchaseOrder.model_validate(e["po"]) if e["po"] else None
            receipts = [GoodsReceipt.model_validate(x) for x in (e["receipts"] or [])]
            vendor = Vendor.model_validate(e["vendor"]) if e["vendor"] else None
            others = [Invoice(invoice_id=x["invoice_id"], tenant_id=inv.tenant_id, bu_id=x["bu_id"], vendor_id=x["vendor_id"],
                              po_ref=None, vendor_invoice_no=x["vendor_invoice_no"], invoice_date=date.fromisoformat(x["invoice_date"]),
                              currency=x["currency"], subtotal=Decimal(x["total"]), tax=Decimal(0), total=Decimal(x["total"]),
                              status=x["status"]) for x in (e["vendor_invoices"] or [])]
            data_complete = e["po_lookup"] != "unavailable" and e["receipts"] is not None and vendor is not None
            findings = []
            if inv.status in PRE_PAYMENT_STATUSES:
                ev_codes = evaluate_invoice(inv, po if e["po_lookup"] == "found" else None, receipts, vendor, others, D.tolerance)
                by = {str(f.code): f for f in ev_codes.findings}
                for c in stored:  # the AP system's holds are authoritative; the engine supplies the explanation
                    f = by.get(c)
                    findings.append({"code": c, "rule_id": f.rule_id if f else None,
                                     "message": f.message if f else "Hold recorded in the AP system",
                                     "details": f.evidence if f else {}})
            payments = [Payment.model_validate(x) for x in (e["payments"] or [])]
            nxt = recommend(inv.status, [HoldCode(c) for c in stored], payments)
            paid = sum((p.amount for p in payments if p.status.value == "PAID"), Decimal("0"))
            amounts = {"total": str(inv.total), "paid": str(paid), "remaining": str(inv.total - paid)} if payments else None
            e["analysis"] = {"status": inv.status.value, "active_holds": stored, "findings": findings, "data_complete": data_complete,
                             "payment_amounts": amounts,
                             "next_actions": [{**a.as_dict(), "description": a.description} for a in nxt]}
        return {"evidence": ev}

    def _view(ev: dict) -> dict:
        """Evidence presented to the explainer: trusted fields + delimited untrusted vendor text."""
        out: dict = {}
        if ev.get("unavailable"):
            out["unavailable_systems"] = sorted(set(ev["unavailable"]))
        if ev.get("not_accessible"):
            out["not_found_or_no_access"] = ev["not_accessible"]
        if "search" in ev:
            out["search"] = ev["search"]
        out["invoices"] = []
        for iid, e in ev.get("invoices", {}).items():
            inv = e["invoice"]
            core = {k: inv.get(k) for k in ("invoice_id", "vendor_id", "po_ref", "vendor_invoice_no", "invoice_date", "currency",
                                           "total", "status", "status_reason")}
            core["lines"] = [{k: l[k] for k in ("sku", "qty", "unit_price", "amount", "po_line_id")} for l in inv.get("lines", [])]
            vt = " ".join(x for x in (inv.get("vendor_memo"), inv.get("attachment_text")) if x)
            out["invoices"].append({
                "invoice": core, "purchase_order": e["po"] and {k: e["po"][k] for k in ("po_id", "status", "currency", "total_amount",
                                                                                         "consumed_amount", "lines")},
                "po_lookup": e["po_lookup"], "vendor": e["vendor"] and {k: e["vendor"][k] for k in ("vendor_id", "name", "status")},
                "payments": e["payments"], "vendor_text": delimit(vt) if vt else None,
                "analysis": e.get("analysis") and {"status": e["analysis"]["status"], "active_holds": e["analysis"]["active_holds"],
                                                   "findings": [{"code": f["code"], "message": f["message"], "details": f["details"]}
                                                                for f in e["analysis"]["findings"]],
                                                   "payment_amounts": e["analysis"].get("payment_amounts"),
                                                   "next_actions": e["analysis"]["next_actions"]}})
        return out

    def _template(ev: dict) -> str:
        parts = []
        for e in _view(ev)["invoices"]:
            a, inv = e["analysis"], e["invoice"]
            s = f"{inv['invoice_id']} is {a['status'].replace('_', ' ').lower()}."
            for f in a["findings"]:
                s += f" Hold {f['code']}: {f['message']}."
            if a["next_actions"]:
                n = a["next_actions"][0]
                s += f" Next action: {n['action']} (owner {n['owner']})."
            parts.append(s)
        if ev.get("unavailable"):
            parts.append("Unavailable: " + ", ".join(sorted(set(ev["unavailable"]))) + ".")
        return " ".join(parts) or "I couldn't retrieve the information needed."

    async def compose_answer(state: HState, config):
        ev = state["evidence"]
        if not ev.get("invoices") and "search" not in ev:
            return {"answer": ""}  # handled deterministically in respond()
        msgs = [SystemMessage(COMPOSE_SYSTEM),
                HumanMessage(json.dumps({"question": state["user_turns"][-1], "evidence": _view(ev)}, default=str))]
        it = Intent(**state["intent"])
        if it.requested_action != "none":
            msgs.append(HumanMessage(ACTION_NOTE.format(tool=it.requested_action)))
        if state.get("grounding_feedback"):
            msgs.append(HumanMessage("Your previous answer contained values not present in the evidence: "
                                     f"{state['grounding_feedback']}. Rewrite it using only evidence values."))
        r = await D.model.ainvoke(msgs, config=config)
        text = r.content if isinstance(r.content, str) else " ".join(b.get("text", "") for b in r.content if isinstance(b, dict))
        return {"answer": text.strip(), "grounding_attempts": state.get("grounding_attempts", 0) + 1}

    async def grounding_check(state: HState, config):
        if not state.get("answer"):
            return {"grounding_feedback": []}
        bad = unsupported(state["answer"], corpus({"e": _view(state["evidence"]), "u": state["user_turns"]}))
        if not bad:
            return {"grounding_feedback": []}
        audit(config, "grounding_failed", attempt=state["grounding_attempts"], unsupported=bad)
        if state["grounding_attempts"] >= 2:
            return {"answer": _template(state["evidence"]), "grounding_feedback": []}
        return {"grounding_feedback": bad}

    def _build_action(state: HState) -> tuple[dict | None, str | None]:
        it = Intent(**state["intent"])
        e = next(iter(state["evidence"].get("invoices", {}).values()), None)
        if e is None:
            return None, None
        inv = e["invoice"]
        iid = inv["invoice_id"]
        reason = (it.action_reason or state["user_turns"][-1])[:200]
        tool = it.requested_action
        if tool == "release_hold":
            holds = inv.get("holds", [])
            if not holds:
                return None, f"{iid} has no active hold to release."
            if len(holds) > 1:
                return None, f"{iid} has several holds ({', '.join(h['code'] for h in holds)}). Which one should I release?"
            return {"tool": tool, "args": {"invoice_id": iid, "hold_id": holds[0]["hold_id"], "reason": reason}}, None
        if tool == "update_po_reference":
            if not it.action_po_id or not re.fullmatch(r"PO-\d{5}", it.action_po_id):
                return None, "Which PO number should the invoice reference?"
            return {"tool": tool, "args": {"invoice_id": iid, "po_id": it.action_po_id}}, None
        if tool in ("reject_invoice",):
            return {"tool": tool, "args": {"invoice_id": iid, "reason": reason}}, None
        if tool == "approve_for_payment":
            return {"tool": tool, "args": {"invoice_id": iid}}, None
        if tool == "create_exception_ticket":
            return {"tool": tool, "args": {"invoice_id": iid, "summary": reason, "assignee_role": "AP_SUPERVISOR"}}, None
        if tool == "place_hold":
            return None, "Placing holds needs a hold code; please specify one."
        return None, None

    async def authorize_action(state: HState, config):
        pr = _principal(config)
        action = state.get("proposed_action")
        if action is None:  # first pass
            action, msg = _build_action(state)
            if action is None:
                return {"action_message": msg, "proposed_action": None}
        inv = next(iter(state["evidence"]["invoices"].values()))["invoice"]
        res = ResourceContext(tenant_id=inv["tenant_id"], bu_id=inv["bu_id"], active_hold_count=len(inv.get("holds", [])))
        d = D.policy.decide(pr, action["tool"], res)
        action = {**action, "hash": action_hash(pr.tenant_id, action["tool"], action["args"]), "decision": d.effect.value,
                  "rule_id": d.rule_id, "reason": d.reason, "approver_roles": list(d.approver_roles)}
        audit(config, "action_authorized" if d.effect != Effect.DENY else "action_denied", d.rule_id, tool=action["tool"],
              action_hash=action["hash"])
        if d.effect == Effect.DENY:
            return {"proposed_action": action, "action_message": f"I can't do that: {d.reason}. This action is not permitted "
                                                                 f"for your role or scope (policy {d.rule_id}). Nothing was changed."}
        return {"proposed_action": action, "action_message": None}

    async def request_approval(state: HState, config):
        pr, a = _principal(config), state["proposed_action"]
        approval_id = "APR-" + a["hash"][:12]
        now = D.clock()
        # Side effect BEFORE interrupt(): this node re-runs from the top on resume, so it must be idempotent.
        D.audit.c.execute("CREATE TABLE IF NOT EXISTS approvals(approval_id TEXT PRIMARY KEY, action_hash TEXT, created REAL, "
                          "expires REAL, decision TEXT, approver TEXT)")
        D.audit.c.execute("INSERT OR IGNORE INTO approvals VALUES (?,?,?,?,NULL,NULL)",
                          [approval_id, a["hash"], now, now + D.approval_ttl_s])
        D.audit.c.commit()
        expires = D.audit.c.execute("SELECT expires FROM approvals WHERE approval_id=?", [approval_id]).fetchone()[0]
        inv = next(iter(state["evidence"]["invoices"].values()))
        card = {"approval_id": approval_id, "action_hash": a["hash"], "tool": a["tool"], "args": a["args"],
                "requester": pr.user_id, "policy_rule": a["rule_id"], "approver_roles": a["approver_roles"], "expires_at": expires,
                # Evidence from systems of record, not LLM prose (ASI09: human-agent trust exploitation)
                "system_evidence": {"status": inv["analysis"]["status"], "active_holds": inv["analysis"]["active_holds"],
                                    "findings": [f["message"] for f in inv["analysis"]["findings"]],
                                    "cause_still_active": bool(inv["analysis"]["active_holds"])}}
        resume = interrupt(card)
        decision = (resume or {}).get("decision")
        approver_id = (resume or {}).get("approver_user_id")
        if decision == "expired" or D.clock() > expires:
            audit(config, "approval_expired", approval_id=approval_id)
            return {"approval": {"status": "expired"}, "action_message": "The approval request expired before anyone approved it. "
                                                                          "Nothing was changed."}
        if decision == "reject":
            audit(config, "approval_rejected", approval_id=approval_id, approver=approver_id)
            return {"approval": {"status": "rejected"}, "action_message": f"The approver ({approver_id}) rejected the request. "
                                                                           "Nothing was changed."}
        approver = D.directory.get(approver_id or "")
        if approver is None:
            return {"approval": {"status": "invalid"}, "action_message": "Approval came from an unknown user. Nothing was changed."}
        v = D.policy.validate_approver(a["tool"], pr, approver)
        if v.effect != Effect.ALLOW:
            audit(config, "approval_invalid", v.rule_id, approval_id=approval_id, approver=approver_id)
            return {"approval": {"status": "invalid"}, "action_message": f"That approval is not valid: {v.reason}. Nothing was changed."}
        if decision == "edit":
            new_args = {**a["args"], **(resume.get("edits") or {})}
            audit(config, "approval_edited", approval_id=approval_id, edits=resume.get("edits"))
            return {"approval": {"status": "edited"}, "proposed_action": {"tool": a["tool"], "args": new_args}}
        if decision != "approve" or resume.get("action_hash") != a["hash"]:
            audit(config, "approval_hash_mismatch", approval_id=approval_id)
            return {"approval": {"status": "invalid"}, "action_message": "The approval does not match the requested action. "
                                                                         "Nothing was changed."}
        D.audit.c.execute("UPDATE approvals SET decision='approve', approver=? WHERE approval_id=?", [approver_id, approval_id])
        D.audit.c.commit()
        audit(config, "approval_granted", approval_id=approval_id, approver=approver_id)
        return {"approval": {"status": "approved", "approval_id": approval_id, "approver": approver_id}}

    async def execute_action(state: HState, config):
        pr, a = _principal(config), state["proposed_action"]
        approval_id = (state.get("approval") or {}).get("approval_id")
        key = idempotency_key(pr.tenant_id, a["tool"], a["args"], approval_id)
        res = await D.client.call(a["tool"], a["args"], idem_key=key)
        if D.crash_hook:
            D.crash_hook("after_execute_write")  # test hook: simulate a crash after the side effect
        audit(config, "action_executed" if res.ok else "action_failed", a.get("rule_id"), tool=a["tool"], idempotency_key=key,
              replayed=res.replayed, status=res.status)
        if not res.ok:
            return {"action_result": {"ok": False, "error": res.error},
                    "action_message": f"I tried to {a['tool'].replace('_', ' ')} but the system returned an error ({res.error}). "
                                      "Please retry later."}
        return {"action_result": {"ok": True, "data": res.data, "replayed": res.replayed}}

    async def verify_postcondition(state: HState, config):
        a, ar = state["proposed_action"], state.get("action_result") or {}
        if not ar.get("ok"):
            return {}
        iid = a["args"]["invoice_id"]
        r = await D.client.call("get_invoice", {"invoice_id": iid})
        ok = r.ok and {
            "release_hold": lambda d: all(h["hold_id"] != a["args"]["hold_id"] for h in d["holds"]),
            "reject_invoice": lambda d: d["status"] == "REJECTED",
            "update_po_reference": lambda d: d["po_ref"] == a["args"]["po_id"],
            "approve_for_payment": lambda d: d["status"] == "SCHEDULED",
        }.get(a["tool"], lambda d: True)(r.data)
        audit(config, "postcondition_ok" if ok else "postcondition_failed", tool=a["tool"])
        new_status = r.data["status"] if r.ok else "unknown"
        approver = (state.get("approval") or {}).get("approver", "n/a")
        msg = (f"Done: {a['tool'].replace('_', ' ')} on {iid} was executed after approval by {approver}. "
               f"Current status: {new_status.replace('_', ' ').lower()}.") if ok else \
              f"The action was sent but I could not verify the result on {iid}; it has been flagged for review."
        return {"action_message": msg}

    async def respond(state: HState, config):
        ev = state.get("evidence") or {}
        if state.get("clarify"):
            final, outcome = state["clarify"], "CLARIFY"
        elif ev.get("not_accessible") and not ev.get("invoices"):
            final = (f"I couldn't find {', '.join(ev['not_accessible'])}, or you don't have access to it. "
                     "Please check the invoice number.")
            outcome = "NOT_FOUND_OR_NO_ACCESS"
        elif not ev.get("invoices") and "search" not in ev:
            final = ("I couldn't retrieve the data needed: the " + ", ".join(sorted(set(ev.get("unavailable", [])))) +
                     " is unavailable right now. Please try again later; I haven't guessed any values.")
            outcome = "SAFE_FAILURE"
        else:
            final = state.get("answer", "")
            if state.get("action_message"):
                executed = (state.get("action_result") or {}).get("ok")
                label = "Before the change: " if executed else ""
                final = f"{state['action_message']}\n\n{label}{final}".strip()
            outcome = "ANSWER"
        targets = list(ev.get("invoices", {}).keys()) or state.get("session_invoices", [])
        audit(config, "response_sent", outcome=outcome)
        return {"final": final, "outcome": outcome, "session_invoices": targets}

    # ------------------------------------------------------------------ edges
    def after_resolve(s):
        return "respond" if s.get("clarify") else "gather_evidence"

    def after_grounding(s):
        if s.get("grounding_feedback"):
            return "compose_answer"
        it = Intent(**s["intent"])
        if it.requested_action != "none" and s["evidence"].get("invoices"):
            return "authorize_action"
        return "respond"

    def after_authorize(s):
        a = s.get("proposed_action")
        if not a or s.get("action_message"):
            return "respond"
        return {"REQUIRE_APPROVAL": "request_approval", "ALLOW": "execute_action"}.get(a["decision"], "respond")

    def after_approval(s):
        st = (s.get("approval") or {}).get("status")
        return {"approved": "execute_action", "edited": "authorize_action"}.get(st, "respond")

    g = StateGraph(HState)
    for name, fn in [("ingest", ingest), ("classify_intent", classify_intent), ("resolve_targets", resolve_targets),
                     ("gather_evidence", gather_evidence), ("evaluate", evaluate), ("compose_answer", compose_answer),
                     ("grounding_check", grounding_check), ("authorize_action", authorize_action),
                     ("request_approval", request_approval), ("execute_action", execute_action),
                     ("verify_postcondition", verify_postcondition), ("respond", respond)]:
        g.add_node(name, fn)
    g.add_edge(START, "ingest")
    g.add_edge("ingest", "classify_intent")
    g.add_edge("classify_intent", "resolve_targets")
    g.add_conditional_edges("resolve_targets", after_resolve, ["respond", "gather_evidence"])
    g.add_edge("gather_evidence", "evaluate")
    g.add_edge("evaluate", "compose_answer")
    g.add_edge("compose_answer", "grounding_check")
    g.add_conditional_edges("grounding_check", after_grounding, ["compose_answer", "authorize_action", "respond"])
    g.add_conditional_edges("authorize_action", after_authorize, ["respond", "request_approval", "execute_action"])
    g.add_conditional_edges("request_approval", after_approval, ["execute_action", "authorize_action", "respond"])
    g.add_edge("execute_action", "verify_postcondition")
    g.add_edge("verify_postcondition", "respond")
    g.add_edge("respond", END)
    return g.compile(checkpointer=checkpointer, name="hardened_invoice_agent")
