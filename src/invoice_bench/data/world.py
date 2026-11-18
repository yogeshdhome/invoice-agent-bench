"""Seeded synthetic world builder: tenants, users, vendors, POs, receipts, background invoices + fixture helpers."""
from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

AS_OF = date(2026, 11, 2)
CENT = Decimal("0.01")
TENANTS = {"t-alpha": ("Synthco Alpha", "USD"), "t-beta": ("Synthco Beta", "EUR"), "t-gamma": ("Synthco Gamma", "USD")}
RESERVED_INVOICES = {"INV-10482"}
RESERVED_POS = {"PO-55120"}
SUFFIXES = ["Synthetic Supplies", "Synthetic Components", "Synthetic Logistics", "Synthetic Fasteners", "Synthetic Tooling"]


def q(x) -> Decimal:
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class POInfo:
    po_id: str
    tenant_id: str
    bu_id: str
    vendor_id: str
    currency: str
    lines: list[tuple[str, str, int, Decimal]]  # (po_line_id, sku, qty, unit_price)

    @property
    def total(self) -> Decimal:
        return sum((qty * p for _, _, qty, p in self.lines), Decimal("0"))


@dataclass
class FixtureRecord:
    invoice_id: str
    tenant_id: str
    bu_id: str
    vendor_id: str
    status: str
    codes: list[str]
    total: Decimal


@dataclass
class World:
    conn: sqlite3.Connection
    rng: random.Random
    counters: dict[str, int] = field(default_factory=lambda: {
        "po": 50000, "pol": 100000, "gr": 80000, "grl": 200000, "inv_bg": 20000, "inv_fx": 10100,
        "invl": 300000, "hold": 10000, "pay": 10000, "vin": 100000, "sku": 1000})
    users: dict[str, dict] = field(default_factory=dict)
    vendors: dict[str, list[str]] = field(default_factory=dict)          # tenant -> active vendor ids
    inactive_vendors: dict[str, list[str]] = field(default_factory=dict)
    fixtures: list[FixtureRecord] = field(default_factory=list)

    # ---------------- ids ----------------
    def _next(self, k: str) -> int:
        self.counters[k] += 1
        return self.counters[k]

    def po_id(self) -> str:
        while (pid := f"PO-{self._next('po'):05d}") in RESERVED_POS:
            pass
        return pid

    def inv_id(self, background: bool) -> str:
        while (iid := f"INV-{self._next('inv_bg' if background else 'inv_fx'):05d}") in RESERVED_INVOICES:
            pass
        return iid

    def vin(self) -> str:
        return f"VI-{self._next('vin')}"

    def money(self, lo: float, hi: float) -> Decimal:
        return q(self.rng.uniform(lo, hi))

    # ---------------- master data ----------------
    def build_master(self) -> None:
        c = self.conn
        vnum = 0
        for tid, (name, _cur) in TENANTS.items():
            short = tid.split("-")[1]
            c.execute("INSERT INTO tenants VALUES (?,?)", [tid, name])
            bus = [f"bu-{short}-1", f"bu-{short}-2"]
            for i, bu in enumerate(bus, 1):
                c.execute("INSERT INTO business_units VALUES (?,?,?)", [bu, tid, f"{name} BU{i}"])
            people = [("clerk-1", [bus[0]], ["AP_CLERK"]), ("clerk-2", [bus[1]], ["AP_CLERK"]),
                      ("supervisor-1", bus, ["AP_SUPERVISOR"]), ("supervisor-2", bus, ["AP_SUPERVISOR"]),
                      ("buyer-1", [bus[0]], ["PROCUREMENT_BUYER"]), ("controller-1", bus, ["FINANCE_CONTROLLER"]),
                      ("controller-2", bus, ["FINANCE_CONTROLLER"]), ("auditor-1", bus, ["AUDITOR_READONLY"])]
            for key, b, roles in people:
                uid = f"u-{short}-{key}"
                c.execute("INSERT INTO users VALUES (?,?,?,?,?)", [uid, tid, json.dumps(b), json.dumps(roles), f"Synthetic {key}"])
                self.users[f"{tid}:{key}"] = {"user_id": uid, "tenant_id": tid, "roles": roles, "bu_ids": b}
            self.vendors[tid], self.inactive_vendors[tid] = [], []
            for i in range(20):
                vnum += 1
                vid = f"V-{vnum:04d}"
                status = "INACTIVE" if i >= 18 else "ACTIVE"
                c.execute("INSERT INTO vendors VALUES (?,?,?,?,?,NULL)",
                          [vid, tid, f"Vendor-{vnum:04d} {SUFFIXES[vnum % 5]}", status, f"SYNBANK-{self.rng.randrange(10**7, 10**8)}"])
                (self.inactive_vendors if status == "INACTIVE" else self.vendors)[tid].append(vid)

    def persona(self, tenant: str, key: str) -> dict:
        return dict(self.users[f"{tenant}:{key}"])

    def bus(self, tenant: str) -> list[str]:
        s = tenant.split("-")[1]
        return [f"bu-{s}-1", f"bu-{s}-2"]

    # ---------------- transactional builders ----------------
    def po(self, tenant: str, bu: str, vendor: str, lines: list[tuple[int, Decimal]], status: str = "OPEN",
           currency: str | None = None, consumed: Decimal = Decimal("0"), po_id: str | None = None,
           created: date | None = None) -> POInfo:
        pid = po_id or self.po_id()
        cur = currency or TENANTS[tenant][1]
        created = created or AS_OF - timedelta(days=self.rng.randrange(30, 120))
        info = POInfo(pid, tenant, bu, vendor, cur, [])
        for qty, price in lines:
            info.lines.append((f"POL-{self._next('pol')}", f"SKU-{self._next('sku'):04d}", qty, q(price)))
        self.conn.execute("INSERT INTO purchase_orders VALUES (?,?,?,?,?,?,?,?,?)",
                          [pid, tenant, bu, vendor, status, cur, str(info.total), str(q(consumed)), created.isoformat()])
        for n, (plid, sku, qty, price) in enumerate(info.lines, 1):
            self.conn.execute("INSERT INTO po_lines VALUES (?,?,?,?,?,?)", [plid, pid, n, sku, qty, str(price)])
        return info

    def set_consumed(self, po_id: str, amount: Decimal) -> None:
        self.conn.execute("UPDATE purchase_orders SET consumed_amount=? WHERE po_id=?", [str(q(amount)), po_id])

    def receipt(self, po: POInfo, qty_by_line: dict[str, int] | None = None, received: date | None = None) -> str:
        gid = f"GR-{self._next('gr'):05d}"
        received = received or AS_OF - timedelta(days=self.rng.randrange(10, 25))
        self.conn.execute("INSERT INTO goods_receipts VALUES (?,?,?)", [gid, po.po_id, received.isoformat()])
        for plid, _sku, qty, _p in po.lines:
            got = qty if qty_by_line is None else qty_by_line.get(plid, 0)
            if got > 0:
                self.conn.execute("INSERT INTO gr_lines VALUES (?,?,?,?)", [f"GRL-{self._next('grl')}", gid, plid, got])
        return gid

    def invoice(self, tenant: str, bu: str, vendor: str, po_ref: str | None,
                lines: list[tuple[str | None, str, int, Decimal]], status: str, holds: list[str] = (),
                memo: str | None = None, attachment: str | None = None, vin: str | None = None,
                inv_date: date | None = None, currency: str | None = None, invoice_id: str | None = None,
                status_reason: str | None = None, background: bool = False) -> tuple[str, list[str]]:
        iid = invoice_id or self.inv_id(background)
        cur = currency or TENANTS[tenant][1]
        inv_date = inv_date or AS_OF - timedelta(days=self.rng.randrange(3, 20))
        subtotal = sum((qty * q(p) for _, _, qty, p in lines), Decimal("0"))
        self.conn.execute("INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          [iid, tenant, bu, vendor, po_ref, vin or self.vin(), inv_date.isoformat(), cur, str(q(subtotal)),
                           "0.00", str(q(subtotal)), status, status_reason, memo, attachment])
        for plid, sku, qty, price in lines:
            self.conn.execute("INSERT INTO invoice_lines VALUES (?,?,?,?,?,?,?)",
                              [f"INVL-{self._next('invl')}", iid, plid, sku, qty, str(q(price)), str(q(qty * q(price)))])
        hold_ids = []
        for code in holds:
            hid = f"H-{self._next('hold'):05d}"
            self.conn.execute("INSERT INTO holds VALUES (?,?,?,?,NULL,NULL,NULL)", [hid, iid, code, AS_OF.isoformat()])
            hold_ids.append(hid)
        if not background:
            self.fixtures.append(FixtureRecord(iid, tenant, bu, vendor, status, sorted(holds), q(subtotal)))
        return iid, hold_ids

    def payment(self, invoice_id: str, amount: Decimal, status: str, scheduled: date | None = None,
                paid: date | None = None, failure: str | None = None) -> str:
        pid = f"PAY-{self._next('pay'):05d}"
        self.conn.execute("INSERT INTO payments VALUES (?,?,?,?,?,?,?)",
                          [pid, invoice_id, str(q(amount)), status, scheduled and scheduled.isoformat(),
                           paid and paid.isoformat(), failure])
        return pid

    # ---------------- background noise ----------------
    def build_background(self, n_pos_per_tenant: int = 133, max_invoices: int = 800) -> None:
        made = 0
        for tid in TENANTS:
            bus = self.bus(tid)
            bus_bg = [bus[0]] if tid == "t-gamma" else bus  # gamma BU2 reserved for open-ended fixtures
            for _ in range(n_pos_per_tenant):
                vendor = self.rng.choice(self.vendors[tid])
                bu = self.rng.choice(bus_bg)
                lines = [(self.rng.randrange(1, 51), self.money(5, 500)) for _ in range(self.rng.randrange(1, 5))]
                status = "CLOSED" if self.rng.random() < 0.1 else "OPEN"
                po = self.po(tid, bu, vendor, lines, status=status)
                r = self.rng.random()
                if status == "OPEN" and r >= 0.85:  # partial or no receipt; no background invoices
                    if r < 0.95:
                        self.receipt(po, {po.lines[0][0]: max(1, po.lines[0][2] // 2)})
                    continue
                gr_date = AS_OF - timedelta(days=self.rng.randrange(20, 90))
                self.receipt(po, None, gr_date)
                consumed = Decimal("0")
                for plid, sku, qty, price in po.lines:  # one invoice per PO line (partitions the PO)
                    if made >= max_invoices:
                        break
                    st = self.rng.choices(["APPROVED", "SCHEDULED", "PAID"], [25, 25, 50])[0]
                    if status == "CLOSED":
                        st = "PAID"
                    d = gr_date + timedelta(days=self.rng.randrange(1, 10))
                    iid, _ = self.invoice(tid, bu, vendor, po.po_id, [(plid, sku, qty, price)], st, inv_date=d, background=True)
                    amt = q(qty * price)
                    if st != "APPROVED":  # consumed = SCHEDULED/PAID/PARTIALLY_PAID only
                        consumed += amt
                    if st == "SCHEDULED":
                        self.payment(iid, amt, "SCHEDULED", scheduled=AS_OF + timedelta(days=self.rng.randrange(1, 15)))
                    elif st == "PAID":
                        self.payment(iid, amt, "PAID", paid=min(d + timedelta(days=30), AS_OF - timedelta(days=1)))
                    made += 1
                self.set_consumed(po.po_id, consumed)
