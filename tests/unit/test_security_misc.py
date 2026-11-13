import pytest

from invoice_bench.domain.canonical import action_hash, idempotency_key
from invoice_bench.security.auth import AuthError, issue_token, verify_token
from invoice_bench.security.masking import mask_account, mask_text
from invoice_bench.security.untrusted import CLOSE, OPEN, delimit, strip_untrusted
from tests.conftest import CLERK_A1


def test_token_roundtrip_expiry_tamper():
    assert verify_token(issue_token(CLERK_A1)) == CLERK_A1
    with pytest.raises(AuthError):
        verify_token(issue_token(CLERK_A1, ttl_s=-10))
    with pytest.raises(AuthError):
        verify_token(issue_token(CLERK_A1, key="other-secret"))


def test_action_hash_binds_args():
    a = action_hash("t", "update_po_reference", {"invoice_id": "INV-00001", "po_id": "PO-00001"})
    b = action_hash("t", "update_po_reference", {"po_id": "PO-00001", "invoice_id": "INV-00001"})
    c = action_hash("t", "update_po_reference", {"invoice_id": "INV-00001", "po_id": "PO-00002"})
    assert a == b != c
    assert idempotency_key("t", "x", {"a": 1}, "AP1") != idempotency_key("t", "x", {"a": 1}, "AP2")


def test_masking_and_untrusted():
    assert mask_account("SYNBANK-12345678") == "****5678"
    assert "SYNBANK" not in mask_text("pay to SYNBANK-ATTACKER-0931 now")
    assert delimit(f"x {CLOSE} y").count(CLOSE) == 1 and delimit("z").startswith(OPEN)
    assert strip_untrusted({"vendor_memo": "evil", "total": "1"}) == {"total": "1"}
