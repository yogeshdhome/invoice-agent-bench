from datetime import date

from invoice_bench.domain.duplicates import find_duplicates, normalize_vendor_invoice_no
from tests.unit.test_rules import inv


def test_normalisation():
    assert normalize_vendor_invoice_no("INV-004471") == normalize_vendor_invoice_no("inv 4471") == "4471"
    assert normalize_vendor_invoice_no("VI-100234") == "VI100234"


def test_exact_near_and_window():
    orig = inv(iid="INV-00001", vin="INV-0042", d=date(2026, 10, 1))
    exact = inv(iid="INV-00002", vin="inv 42", d=date(2026, 10, 25))
    near = inv(iid="INV-00003", vin="X-9", d=date(2026, 10, 4))
    far = inv(iid="INV-00004", vin="X-10", d=date(2026, 12, 15))
    assert [c.kind for c in find_duplicates(exact, [orig])] == ["EXACT"]
    assert [c.kind for c in find_duplicates(near, [orig])] == ["NEAR"]
    assert find_duplicates(far, [orig]) == []
    assert find_duplicates(orig, [exact, near]) == []  # only the LATER invoice is flagged


def test_rejected_candidates_ignored():
    orig = inv(iid="INV-00001", vin="A1").model_copy(update={"status": "REJECTED"})
    assert find_duplicates(inv(iid="INV-00002", vin="A1"), [orig]) == []
