from decimal import Decimal as D

from hypothesis import given, settings
from hypothesis import strategies as st

from invoice_bench.domain.canonical import action_hash, idempotency_key
from invoice_bench.domain.models import HoldCode
from invoice_bench.domain.rules import Tolerance, evaluate_invoice
from tests.unit.test_rules import VENDOR, gr, inv, po

prices = st.decimals(min_value=D("1.00"), max_value=D("999.99"), places=2)


@settings(max_examples=300, deadline=None)
@given(po_price=prices, bump=st.decimals(min_value=D("0.00"), max_value=D("50.00"), places=2), qty=st.integers(1, 50))
def test_price_tolerance_monotonic(po_price, bump, qty):
    """If an invoice price fails, any higher price also fails; if it passes, any lower price passes."""
    def fails(p):
        return HoldCode.PRICE_VARIANCE in evaluate_invoice(inv(str(p), qty), po(str(po_price), qty, total="999999"), gr(qty),
                                                           VENDOR, [], Tolerance()).codes
    hi = po_price + bump
    if fails(po_price + bump / 2):
        assert fails(hi)
    if not fails(hi):
        assert not fails(po_price + bump / 2)
    assert not fails(po_price)  # exact match never fails


@given(args=st.dictionaries(st.sampled_from(["invoice_id", "po_id", "reason", "hold_id"]), st.text(max_size=20), min_size=1))
def test_hash_and_key_are_order_independent_and_deterministic(args):
    rev = dict(reversed(list(args.items())))
    assert action_hash("t", "x", args) == action_hash("t", "x", rev)
    assert idempotency_key("t", "x", args, "a") == idempotency_key("t", "x", rev, "a")


@settings(max_examples=25, deadline=None)
@given(n=st.integers(2, 6))
def test_n_identical_writes_yield_one_effect(n, tmp_path_factory):
    import shutil
    import sqlite3
    from fastapi.testclient import TestClient
    from invoice_bench.data.generate import generate
    from invoice_bench.services.app import create_app
    from tests.conftest import SUP_A, bearer
    base = tmp_path_factory.getbasetemp() / "prop_ds"
    if not (base / "world.sqlite").exists():
        generate(20261111, base)
    db = tmp_path_factory.mktemp("w") / "world.sqlite"
    shutil.copy(base / "world.sqlite", db)
    c = TestClient(create_app(str(db), today="2026-11-02"))
    h = {**bearer(SUP_A), "Idempotency-Key": "idem-prop"}
    codes = [c.post("/invoices/INV-10482/holds", json={"code": "QTY_VARIANCE", "reason": "p"}, headers=h).status_code for _ in range(n)]
    assert set(codes) == {200}
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM holds WHERE invoice_id='INV-10482' AND reason='p'").fetchone()[0] == 1
