"""v1.0.1 tests added after the publication validation (V-13, V-14, V-15). Offline, no tokens."""
import asyncio
import shutil
import sqlite3
import threading
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from invoice_bench.observability.audit import AuditLog
from invoice_bench.security.auth import Principal, issue_token
from invoice_bench.services.app import create_app
from invoice_bench.tools.client import ToolResult
from invoice_bench.tools.resilient import ResilientClient, RetryPolicy
from tests.graph.helpers import Rig, scenarios


@pytest.fixture(scope="module")
def S(dataset):
    return scenarios(dataset)


def _copy(dataset, tmp):
    p = tmp / "world.sqlite"
    shutil.copy(dataset / "world.sqlite", p)
    return p


def test_concurrent_same_key_writes_collapse_to_one_effect(dataset, tmp_path):
    db = _copy(dataset, tmp_path)
    app = create_app(str(db), today="2026-11-02")
    sup = Principal(user_id="u-alpha-supervisor-1", tenant_id="t-alpha", bu_ids=("bu-alpha-1", "bu-alpha-2"), roles=("AP_SUPERVISOR",))
    h = {"Authorization": f"Bearer {issue_token(sup)}"}
    res, lock = Counter(), threading.Lock()

    def go(key):
        r = TestClient(app).post("/invoices/INV-10482/holds", json={"code": "QTY_VARIANCE", "reason": "conc"},
                                 headers={**h, "Idempotency-Key": key})
        with lock:
            res[(r.status_code, r.headers.get("Idempotent-Replayed"))] += 1

    ts = [threading.Thread(target=go, args=("idem-same",)) for _ in range(12)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    n = sqlite3.connect(db).execute("SELECT COUNT(*) FROM holds WHERE invoice_id='INV-10482' AND reason='conc'").fetchone()[0]
    assert n == 1 and res[(200, None)] == 1 and res[(200, "true")] == 11
    # Different keys are different requests: the service does NOT de-duplicate them (documented limitation).
    ts = [threading.Thread(target=go, args=(f"idem-{i}",)) for i in range(3)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sqlite3.connect(db).execute("SELECT COUNT(*) FROM holds WHERE reason='conc'").fetchone()[0] == 4


def _release_rig(S, dataset, tmp, clock):
    sc = S["AP-001"]
    inv = sc.fixtures["primary_invoice"]
    script = [{"intent": "perform_action", "invoice_ids": [inv], "requested_action": "release_hold"}, f"{inv} is on hold."] * 2
    r = Rig(_copy(dataset, tmp), sc.persona.model_dump(), script)
    r.deps.clock = lambda: clock[0]
    r.deps.approval_ttl_s = 3600
    return sc, inv, r


def test_time_based_expiry_blocks_execution(S, dataset, tmp_path):
    clock = [1_000_000.0]
    sc, inv, r = _release_rig(S, dataset, tmp_path, clock)
    card = r.invoke({"new_turn": sc.turns[0].content})["__interrupt__"][0].value
    clock[0] += 3601                                   # approver answers after the TTL
    out = r.resume({"decision": "approve", "approver_user_id": "u-alpha-controller-1", "action_hash": card["action_hash"]})
    assert "expired" in out["final"] and r.q("SELECT COUNT(*) FROM action_log") == [(0,)]


def test_repeated_request_gets_a_fresh_approval_not_the_expired_one(S, dataset, tmp_path):
    clock = [1_000_000.0]
    sc, inv, r = _release_rig(S, dataset, tmp_path, clock)
    card1 = r.invoke({"new_turn": sc.turns[0].content})["__interrupt__"][0].value
    clock[0] += 3601
    r.resume({"decision": "approve", "approver_user_id": "u-alpha-controller-1", "action_hash": card1["action_hash"]})
    card2 = r.invoke({"new_turn": sc.turns[0].content})["__interrupt__"][0].value   # same action, new request
    assert card2["action_hash"] == card1["action_hash"] and card2["approval_id"] != card1["approval_id"]
    assert card2["expires_at"] > clock[0]                                          # v1.0.0 re-used the expired row
    out = r.resume({"decision": "approve", "approver_user_id": "u-alpha-controller-1", "action_hash": card2["action_hash"]})
    assert "Done" in out["final"] and r.q("SELECT COUNT(*) FROM action_log") == [(1,)]


def test_circuit_breaker_opens_after_five_failed_calls_and_fails_fast():
    calls = Counter()

    class Inner:
        tracer = None

        async def attempt(self, tool, args, idem_key=None):
            calls[tool] += 1
            return ToolResult(False, 503, error="HTTP 503")

        def record(self, *a, **k):
            pass

    async def no_sleep(_):
        return None

    rc = ResilientClient(Inner(), RetryPolicy(max_attempts=1, breaker_threshold=5, breaker_reset_s=30), sleep=no_sleep)
    for _ in range(5):
        assert asyncio.run(rc.call("get_invoice", {"invoice_id": "INV-00001"})).error == "HTTP 503"
    res = asyncio.run(rc.call("get_invoice", {"invoice_id": "INV-00001"}))
    assert res.error == "circuit open" and calls["get_invoice"] == 5     # sixth call never reached the service


def test_audit_log_is_append_only():
    a = AuditLog(None)
    a.log("r1", "u", "request_received")
    with pytest.raises(sqlite3.DatabaseError):
        a.c.execute("UPDATE audit SET event='tampered'")
    with pytest.raises(sqlite3.DatabaseError):
        a.c.execute("DELETE FROM audit")
    assert [e["event"] for e in a.events()] == ["request_received"]
