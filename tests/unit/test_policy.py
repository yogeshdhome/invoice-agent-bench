from pathlib import Path

import pytest

from invoice_bench.security.policy import Effect, PolicyEngine, ResourceContext
from invoice_bench.tools.contracts import CONTRACTS
from tests.conftest import CLERK_A1, CLERK_B1, SUP_A, SVC

from invoice_bench.security.auth import Principal

ENGINE = PolicyEngine.from_yaml(Path("config/policies.yaml"))
RES = ResourceContext(tenant_id="t-alpha", bu_id="bu-alpha-1", active_hold_count=1)
CTRL1 = Principal(user_id="u-alpha-controller-1", tenant_id="t-alpha", bu_ids=("bu-alpha-1",), roles=("FINANCE_CONTROLLER",))
CTRL2 = CTRL1.model_copy(update={"user_id": "u-alpha-controller-2"})
BUYER = Principal(user_id="u-alpha-buyer-1", tenant_id="t-alpha", bu_ids=("bu-alpha-1",), roles=("PROCUREMENT_BUYER",))


@pytest.mark.parametrize("who,tool,res,effect,rule", [
    (CLERK_A1, "get_invoice", RES, Effect.ALLOW, "RD-01"),
    (CLERK_B1, "get_invoice", RES, Effect.DENY, "SC-01"),
    (CLERK_A1, "get_invoice", ResourceContext(tenant_id="t-alpha", bu_id="bu-alpha-2"), Effect.DENY, "SC-02"),
    (SUP_A, "get_invoice", ResourceContext(tenant_id="t-alpha", bu_id="bu-alpha-2"), Effect.ALLOW, "RD-01"),
    (CLERK_A1, "release_hold", RES, Effect.DENY, "AP-07:ROLE"),
    (SUP_A, "release_hold", RES, Effect.REQUIRE_APPROVAL, "AP-07"),
    (BUYER, "reject_invoice", RES, Effect.DENY, "AP-08:ROLE"),
    (BUYER, "update_po_reference", RES, Effect.REQUIRE_APPROVAL, "AP-09"),
    (CLERK_A1, "place_hold", RES, Effect.ALLOW, "AP-03"),
    (CTRL1, "approve_for_payment", RES, Effect.DENY, "FC-01:PRECONDITION"),
    (CTRL1, "approve_for_payment", ResourceContext(tenant_id="t-alpha", bu_id="bu-alpha-1", active_hold_count=0),
     Effect.REQUIRE_APPROVAL, "FC-01"),
    (SUP_A, "update_vendor", RES, Effect.DENY, "VM-01"),
    (CTRL1, "update_vendor", RES, Effect.DENY, "VM-01"),
    (SVC, "get_invoice", RES, Effect.DENY, "POL-SA"),
    (SUP_A, "drop_tables", RES, Effect.DENY, "POL-00"),
])
def test_decisions(who, tool, res, effect, rule):
    d = ENGINE.decide(who, tool, res)
    assert (d.effect, d.rule_id) == (effect, rule)


def test_kill_switch_blocks_writes_not_reads():
    ks = PolicyEngine.from_yaml(Path("config/policies.yaml"), writes_enabled=False)
    assert ks.decide(SUP_A, "release_hold", RES).rule_id == "KS-01"
    assert ks.decide(SUP_A, "get_invoice", RES).effect == Effect.ALLOW


def test_segregation_of_duties():
    assert ENGINE.validate_approver("approve_for_payment", CTRL1, CTRL1).rule_id == "SOD-01"
    assert ENGINE.validate_approver("approve_for_payment", CTRL1, CTRL2).effect == Effect.ALLOW
    assert ENGINE.validate_approver("release_hold", SUP_A, CLERK_A1).rule_id == "SOD-03"
    assert ENGINE.validate_approver("release_hold", SUP_A, CLERK_B1).rule_id == "SOD-02"


def test_contracts_and_policy_agree():
    assert set(CONTRACTS) == set(ENGINE.tools)
    for name, c in CONTRACTS.items():
        assert c.side_effect == ENGINE.side_effect(name), name
