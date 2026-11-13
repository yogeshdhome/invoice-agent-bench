"""Shared operating-procedure text so both arms get the same domain knowledge (fairness control)."""
from pathlib import Path

import yaml

from ..domain.next_action import HOLD_ACTIONS, PAYMENT_FAILED_ACTION, STATUS_ACTIONS

ROLE_TEXT = (
    "AP_CLERK: view invoices in own business units, place holds, create exception tickets. "
    "AP_SUPERVISOR: view all business units in the tenant; also release holds, reject invoices, update PO references. "
    "PROCUREMENT_BUYER: view own business units, update PO references, create exception tickets. "
    "FINANCE_CONTROLLER: view all business units; approve invoices for payment (only with no active holds). "
    "AUDITOR_READONLY: read-only. Nobody may change vendor master or bank details through this assistant."
)
TOLERANCE_TEXT = ("3-way match: a line fails price matching if the invoice unit price exceeds the PO price by more than 2.00% "
                  "or by more than 50.00 in total for the line; invoiced quantity must not exceed received quantity; "
                  "an invoice may exceed the remaining PO value by at most 10%.")


def procedure_text() -> str:
    lines = [f"- {c.value}: {a.action} (owner {a.owner}). {a.description}" for c, a in HOLD_ACTIONS.items()]
    lines += [f"- status {s.value} with no holds: {a.action} (owner {a.owner})." for s, a in STATUS_ACTIONS.items()]
    lines.append(f"- failed payment: {PAYMENT_FAILED_ACTION.action} (owner {PAYMENT_FAILED_ACTION.owner}).")
    return "Next-action procedure by hold code / status:\n" + "\n".join(lines)


def approver_text(policy_path: str | Path = "config/policies.yaml") -> str:
    """Approver roles per action, rendered from the policy file the hardened arm enforces (no drift between arms)."""
    tools = yaml.safe_load(Path(policy_path).read_text())["tools"]
    parts = [f"{t}: requested by {'/'.join(v['allow_roles'])}; approved by {'/'.join(v['approver_roles'])}"
             for t, v in tools.items() if v.get("approval") == "required"]
    return "Approval rules (approver must be a different person from the requester): " + "; ".join(parts) + "."
