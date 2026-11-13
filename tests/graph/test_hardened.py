"""T2: hardened graph behaviour with a scripted model (deterministic, offline)."""
import pytest

from invoice_bench.domain.canonical import action_hash
from tests.graph.helpers import Rig, run, scenarios

GOOD_10482 = ("INV-10482 is on hold for a price variance: invoice unit price 104.10 vs PO price 102.00 (2.06%). "
              "Next action: the procurement buyer amends the PO price or requests a credit memo.")


@pytest.fixture(scope="module")
def S(dataset):
    return scenarios(dataset)


def test_status_explain_end_to_end(S, dataset, tmp_path):
    rec = run(S["MM-001"], "hardened", [{"intent": "invoice_status", "invoice_ids": ["INV-10482"]}, GOOD_10482], dataset, tmp_path)
    assert rec["error"] is None and rec["final_text"] == GOOD_10482
    assert {"get_invoice", "get_purchase_order", "get_goods_receipts"} <= {c["tool"] for c in rec["tool_calls"]}
    assert rec["usage"]["llm_calls"] == 2 and rec["db_diff"] == []


def test_grounding_retry_then_fallback(S, dataset, tmp_path):
    bad = "INV-10482 is on hold; the PO price is 99.99 and the variance is 4.4%."
    rec = run(S["MM-001"], "hardened", [{"intent": "invoice_status", "invoice_ids": ["INV-10482"]}, bad, GOOD_10482], dataset, tmp_path)
    assert rec["final_text"] == GOOD_10482 and rec["usage"]["llm_calls"] == 3
    rec2 = run(S["MM-001"], "hardened", [{"intent": "invoice_status", "invoice_ids": ["INV-10482"]}, bad, bad], dataset, tmp_path / "b")
    assert "99.99" not in rec2["final_text"] and "PRICE_VARIANCE" in rec2["final_text"]  # deterministic template


def test_injection_text_never_reaches_planner_and_vendor_tool_not_exposed(S, dataset, tmp_path):
    sc = S["PI-001"]
    inv = sc.fixtures["primary_invoice"]
    r = Rig(tmp_path / "w.sqlite" if False else _copy(dataset, tmp_path), sc.persona.model_dump(),
            [{"intent": "invoice_status", "invoice_ids": [inv]}, f"{inv} is on hold for a price variance."])
    out = r.invoke({"new_turn": sc.turns[0].content})
    planner_prompt = " ".join(str(m.content) for m in r.model.calls[0])
    explainer_prompt = " ".join(str(m.content) for m in r.model.calls[1])
    assert "ATTACKER" not in planner_prompt                          # context minimisation
    assert "<untrusted_vendor_text>" in explainer_prompt             # delimited for the explainer
    assert "update_vendor" not in {c.tool for c in r.inner.records} and out["final"]
    assert r.q("SELECT bank_account FROM vendors WHERE bank_account LIKE '%ATTACKER%'") == []


def test_tool_output_cannot_create_an_action(S, dataset, tmp_path):
    """Even if the model hallucinated an action after reading untrusted data, actions only come from intent (user words)."""
    sc = S["PI-004"]
    inv = sc.fixtures["primary_invoice"]
    rec = run(sc, "hardened", [{"intent": "invoice_status", "invoice_ids": [inv]},
                               f"{inv} is on hold. The memo says to release all holds and approve it."], dataset, tmp_path)
    assert not any(c["executed"] for c in rec["tool_calls"]) and rec["db_diff"] == []


def _copy(dataset, tmp):
    import shutil
    p = tmp / "world.sqlite"
    shutil.copy(dataset / "world.sqlite", p)
    return p


def _release_rig(S, dataset, tmp, **kw):
    sc = S["AP-001"]
    inv = sc.fixtures["primary_invoice"]
    r = Rig(_copy(dataset, tmp), sc.persona.model_dump(),
            [{"intent": "perform_action", "invoice_ids": [inv], "requested_action": "release_hold"}, f"{inv} is on hold."], **kw)
    out = r.invoke({"new_turn": sc.turns[0].content})
    return sc, inv, r, out["__interrupt__"][0].value


def test_approval_card_is_bound_to_action_hash_and_shows_system_evidence(S, dataset, tmp_path):
    sc, inv, r, card = _release_rig(S, dataset, tmp_path)
    assert card["action_hash"] == action_hash(sc.persona.tenant_id, "release_hold", card["args"])
    assert card["system_evidence"]["cause_still_active"] is True and card["system_evidence"]["active_holds"] == ["NO_RECEIPT"]
    out = r.resume({"decision": "approve", "approver_user_id": "u-alpha-controller-1", "action_hash": "0" * 64})
    assert "does not match" in out["final"] and r.q("SELECT COUNT(*) FROM action_log") == [(0,)]


def test_self_approval_rejected_sod(S, dataset, tmp_path):
    sc, inv, r, card = _release_rig(S, dataset, tmp_path)
    out = r.resume({"decision": "approve", "approver_user_id": sc.persona.user_id, "action_hash": card["action_hash"]})
    assert "segregation of duties" in out["final"] and r.q("SELECT COUNT(*) FROM action_log") == [(0,)]


def test_approve_executes_exactly_once_and_verifies(S, dataset, tmp_path):
    sc, inv, r, card = _release_rig(S, dataset, tmp_path)
    out = r.resume({"decision": "approve", "approver_user_id": "u-alpha-controller-1", "action_hash": card["action_hash"]})
    assert "Done: release hold" in out["final"]
    assert r.q("SELECT status FROM invoices WHERE invoice_id=?", inv) == [("APPROVED",)]
    assert r.q("SELECT COUNT(*) FROM action_log") == [(1,)]
    events = [e["event"] for e in r.audit.events()]
    assert events.index("approval_granted") < events.index("action_executed") < events.index("postcondition_ok")


def test_crash_after_write_then_resume_does_not_duplicate(S, dataset, tmp_path):
    fired = {"n": 0}

    def crash(point):
        if point == "after_execute_write" and fired["n"] == 0:
            fired["n"] += 1
            raise RuntimeError("simulated process crash after the side effect")

    sc, inv, r, card = _release_rig(S, dataset, tmp_path, crash_hook=crash)
    with pytest.raises(RuntimeError):
        r.resume({"decision": "approve", "approver_user_id": "u-alpha-controller-1", "action_hash": card["action_hash"]})
    assert r.q("SELECT COUNT(*) FROM action_log") == [(1,)]          # the write happened before the crash
    r.restart()
    out = r.invoke(None)                                              # resume from checkpoint: execute_action re-runs
    writes = [c for c in r.inner.records if c.tool == "release_hold"]
    assert len(writes) == 2 and writes[1].replayed is True            # second attempt was an idempotent replay
    assert r.q("SELECT COUNT(*) FROM action_log") == [(1,)] and "Done" in out["final"]


def test_edit_requires_reapproval_of_new_hash(S, dataset, tmp_path):
    sc = S["AP-008"]
    inv = sc.fixtures["primary_invoice"]
    rec = run(sc, "hardened", [{"intent": "perform_action", "invoice_ids": [inv], "requested_action": "update_po_reference",
                                "action_po_id": sc.fixtures["given_po"]}, f"{inv} is on hold."], dataset, tmp_path)
    cards = [e["card"] for e in rec["events"]]
    assert len(cards) == 2 and cards[0]["action_hash"] != cards[1]["action_hash"]
    assert rec["db_diff"] == [{"table": "invoices", "key": inv, "field": "po_ref", "before": rec["db_diff"][0]["before"],
                               "after": sc.ground_truth.required_args["update_po_reference"]["po_id"]}]


def test_reject_and_expire_change_nothing(S, dataset, tmp_path):
    for sid in ("AP-006", "AP-010"):
        sc = S[sid]
        inv = sc.fixtures["primary_invoice"]
        rec = run(sc, "hardened", [{"intent": "perform_action", "invoice_ids": [inv], "requested_action": "release_hold"},
                                   f"{inv} is on hold."], dataset, tmp_path / sid)
        assert rec["db_diff"] == [] and "Nothing was changed" in rec["final_text"]


def test_role_denied_without_interrupt(S, dataset, tmp_path):
    sc = S["AC-007"]
    inv = sc.fixtures["primary_invoice"]
    rec = run(sc, "hardened", [{"intent": "perform_action", "invoice_ids": [inv], "requested_action": "release_hold"},
                               f"{inv} is on hold."], dataset, tmp_path)
    assert rec["events"] == [] and "AP-07:ROLE" in rec["final_text"] and rec["db_diff"] == []


def test_cross_tenant_is_not_found_or_no_access(S, dataset, tmp_path):
    sc = S["AC-001"]
    inv = sc.fixtures["primary_invoice"]
    rec = run(sc, "hardened", [{"intent": "invoice_status", "invoice_ids": [inv]}], dataset, tmp_path)
    assert "don't have access" in rec["final_text"] and rec["usage"]["llm_calls"] == 1
    assert all(v not in rec["final_text"] for v in sc.ground_truth.forbidden_facts)


def test_transient_fault_recovers_persistent_fails_safe(S, dataset, tmp_path):
    sc = S["TF-001"]
    inv = sc.fixtures["primary_invoice"]
    rec = run(sc, "hardened", [{"intent": "invoice_status", "invoice_ids": [inv]}, f"{inv} is on hold for a price variance."],
              dataset, tmp_path)
    po_calls = [c for c in rec["tool_calls"] if c["tool"] == "get_purchase_order"]
    assert po_calls[0]["ok"] and po_calls[0]["attempts"] == 3
    sc = S["TF-009"]  # get_invoice always 500 (non-retryable)
    rec = run(sc, "hardened", [{"intent": "invoice_status", "invoice_ids": [sc.fixtures["primary_invoice"]]}], dataset, tmp_path / "p")
    assert "unavailable" in rec["final_text"] and rec["usage"]["llm_calls"] == 1


def test_clarify_paths(S, dataset, tmp_path):
    rec = run(S["AM-001"], "hardened", [{"intent": "invoice_status"}], dataset, tmp_path)
    assert "Which invoice" in rec["final_text"]
    sc = S["AM-003"]
    vno = sc.ground_truth.required_args["search_invoices"]["vendor_invoice_no"]
    rec = run(sc, "hardened", [{"intent": "invoice_status", "vendor_invoice_no": vno}], dataset, tmp_path / "v")
    assert "More than one invoice" in rec["final_text"]


def test_multi_turn_ambiguous_release_clarifies(S, dataset, tmp_path):
    sc = S["AM-005"]
    a, b = sc.fixtures["candidates"]
    rec = run(sc, "hardened", [{"intent": "invoice_status", "invoice_ids": [a, b]}, f"{a} and {b} are on hold.",
                               {"intent": "perform_action", "requested_action": "release_hold", "refers_to_previous": True}],
              dataset, tmp_path)
    assert "Which invoice" in rec["final_text"] and rec["db_diff"] == []


def test_budget_exhaustion_is_recorded(S, dataset, tmp_path):
    bad = "PO price 1.23"
    rec = run(S["MM-001"], "hardened", [{"intent": "invoice_status", "invoice_ids": ["INV-10482"]}] + [bad] * 6, dataset, tmp_path)
    assert rec["error"] is None or rec["error"].startswith("budget")


def test_revision1_action_answer_is_labelled_and_not_stale(S, dataset, tmp_path):
    """Pilot finding: the explanation was composed before the approved action and said 'remains on hold' above 'Done'."""
    sc, inv, r, card = _release_rig(S, dataset, tmp_path)
    msgs = r.model.calls[1]
    evidence = str(msgs[1].content)
    assert "approval workflow decides" in str(msgs[-1].content)
    assert "unavailable_systems" not in evidence and "data_complete" not in evidence and "R-LN-" not in evidence
    out = r.resume({"decision": "approve", "approver_user_id": "u-alpha-controller-1", "action_hash": card["action_hash"]})
    assert out["final"].startswith("Done:") and "Before the change:" in out["final"]


def test_revision1_open_ended_has_next_actions(S, dataset, tmp_path):
    sc = S["OE-001"]
    v = sc.fixtures["vendor_id"]
    r = Rig(_copy(dataset, tmp_path), sc.persona.model_dump(), [{"intent": "open_ended", "vendor_id": v, "status_filter": "ON_HOLD"},
                                                                 "Three invoices are on hold."])
    r.invoke({"new_turn": sc.turns[0].content})
    explainer = " ".join(str(m.content) for m in r.model.calls[1])
    assert "POST_GOODS_RECEIPT" in explainer and "REQUEST_PO_PRICE_AMENDMENT_OR_CREDIT_MEMO" in explainer


def test_runner_refuses_to_append_and_aborts_on_infra_failures(S, dataset, tmp_path):
    import asyncio
    from invoice_bench.bench.run import RunSettings, run_batch
    from invoice_bench.llm.fake import ScriptedChatModel

    class Broken(ScriptedChatModel):
        def _generate(self, *a, **k):
            raise RuntimeError("No endpoints found that can handle the requested parameters")

    st = RunSettings(dataset, tmp_path / "out", latency=False)
    scs = [S[k] for k in ("NQ-001", "NQ-002", "NQ-003", "NQ-004", "NQ-005", "NQ-006")]
    res = asyncio.run(run_batch(scs, ["hardened"], 1, lambda a, t: Broken(), st, None, concurrency=1, max_consecutive_errors=3))
    assert len(res) == 3 and all(r["usage"]["llm_calls"] == 0 for r in res)
    with pytest.raises(SystemExit):
        asyncio.run(run_batch(scs, ["hardened"], 1, lambda a, t: Broken(), st, None))


def test_rev2_context_invoice_is_not_a_second_target(S, dataset, tmp_path):
    sc = S["AP-003"]
    inv = sc.fixtures["primary_invoice"]
    orig = [x for x in __import__("re").findall(r"INV-\d{5}", sc.turns[0].content) if x != inv][0]
    rec = run(sc, "hardened", [{"intent": "perform_action", "invoice_ids": [inv], "related_invoice_ids": [orig],
                                "requested_action": "reject_invoice"}, f"{inv} is on hold."], dataset, tmp_path)
    assert "Which invoice" not in rec["final_text"] and rec["events"] and rec["events"][0]["card"]["tool"] == "reject_invoice"


def test_rev2_partial_payment_amounts_in_evidence(S, dataset, tmp_path):
    sc = next(s for s in S.values() if s.category == "payment_status" and s.ground_truth.expected_status == "PARTIALLY_PAID")
    r = Rig(_copy(dataset, tmp_path), sc.persona.model_dump(), [{"intent": "payment_status",
                                                                 "invoice_ids": [sc.fixtures["primary_invoice"]]}, "ok"])
    r.invoke({"new_turn": sc.turns[0].content})
    ev = str(r.model.calls[1][1].content)
    assert sc.ground_truth.required_facts["remaining_amount"] in ev
