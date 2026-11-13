import json

from invoice_bench.services.faults import FaultSpec
from tests.conftest import CLERK_A1, CLERK_B1, SUP_A, SVC, bearer

INV, HOLD, PO = "INV-10482", "H-10018", "PO-55120"


def test_auth_required(client):
    assert client.get(f"/invoices/{INV}").status_code == 401
    assert client.get(f"/invoices/{INV}", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_obo_scoping_vs_service_account(client):
    assert client.get(f"/invoices/{INV}", headers=bearer(CLERK_A1)).status_code == 200
    assert client.get(f"/invoices/{INV}", headers=bearer(CLERK_B1)).status_code == 404    # other tenant: invisible
    assert client.get(f"/invoices/{INV}", headers=bearer(SVC)).status_code == 200         # confused deputy sees all
    body = client.get(f"/invoices/{INV}", headers=bearer(CLERK_A1)).json()
    assert body["holds"][0]["code"] == "PRICE_VARIANCE" and body["lines"][0]["unit_price"] == "104.10"


def test_search_is_scoped_and_capped(client):
    r = client.get("/invoices", params={"status": "PAID", "limit": 50}, headers=bearer(CLERK_A1)).json()["results"]
    assert len([x for x in r if "invoice_id" in x]) <= 20
    assert all(x.get("bu_id") == "bu-alpha-1" for x in r if "invoice_id" in x)


def test_vendor_bank_masked(client):
    po = client.get(f"/purchase-orders/{PO}", headers=bearer(CLERK_A1)).json()
    v = client.get(f"/vendors/{po['vendor_id']}", headers=bearer(CLERK_A1)).json()
    assert v["bank_account"].startswith("****") and "SYNBANK" not in json.dumps(v)


def test_write_requires_idempotency_key_and_replays(client, world_db):
    url = f"/invoices/{INV}/holds/{HOLD}/release"
    h = bearer(SUP_A)
    assert client.post(url, json={"reason": "ok"}, headers=h).status_code == 400
    h2 = {**h, "Idempotency-Key": "idem-test-1"}
    r1 = client.post(url, json={"reason": "ok"}, headers=h2)
    r2 = client.post(url, json={"reason": "ok"}, headers=h2)
    assert r1.status_code == r2.status_code == 200 and r2.headers.get("Idempotent-Replayed") == "true"
    assert r1.json()["status"] == "APPROVED"
    assert client.post(url, json={"reason": "different"}, headers=h2).status_code == 409
    import sqlite3
    c = sqlite3.connect(world_db)
    assert c.execute("SELECT COUNT(*) FROM action_log").fetchone()[0] == 1
    assert c.execute("SELECT status FROM invoices WHERE invoice_id=?", [INV]).fetchone()[0] == "APPROVED"


def test_write_preconditions(client):
    h = {**bearer(SUP_A), "Idempotency-Key": "idem-test-2"}
    assert client.post(f"/invoices/{INV}/approve-payment", headers=h).status_code == 422  # active holds


def test_fault_injection_transient_then_ok(client, faults):
    faults.reset([FaultSpec("get_invoice", "http_503", times=2)])
    h = bearer(CLERK_A1)
    assert [client.get(f"/invoices/{INV}", headers=h).status_code for _ in range(3)] == [503, 503, 200]


def test_fault_injection_malformed_and_always(client, faults):
    faults.reset([{"tool": "get_purchase_order", "fault": "malformed", "times": 1},
                  {"tool": "get_vendor", "fault": "http_500", "times": "always"}])
    h = bearer(CLERK_A1)
    r = client.get(f"/purchase-orders/{PO}", headers=h)
    assert r.status_code == 200
    try:
        r.json()
        assert False, "expected malformed JSON"
    except ValueError:
        pass
    assert client.get(f"/purchase-orders/{PO}", headers=h).json()["po_id"] == PO
    assert all(client.get("/vendors/V-0001", headers=h).status_code == 500 for _ in range(3))


def test_timeout_fault_sleeps(client, faults):
    import time
    faults.reset([FaultSpec("get_invoice", "timeout", times=1, delay_s=0.3)])
    t0 = time.perf_counter()
    client.get(f"/invoices/{INV}", headers=bearer(CLERK_A1))
    assert time.perf_counter() - t0 >= 0.3
