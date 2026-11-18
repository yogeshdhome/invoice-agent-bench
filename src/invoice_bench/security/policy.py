"""Policy engine: decides Allow / Deny / RequireApproval at the tool boundary (SEC-02).

The LLM never makes these decisions; it can only *propose* tool calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel

from .auth import Principal


class Effect(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


@dataclass(frozen=True)
class Decision:
    effect: Effect
    rule_id: str
    reason: str
    approver_roles: tuple[str, ...] = ()


class ResourceContext(BaseModel):
    tenant_id: str
    bu_id: str | None = None
    active_hold_count: int | None = None


READ = "READ"


class PolicyEngine:
    def __init__(self, policy: dict, writes_enabled: bool = True):
        self.p = policy
        self.tools: dict = policy["tools"]
        self.all_bu_roles = tuple(policy["all_bu_roles"])
        self.read_roles = tuple(policy["read_roles"])
        self.writes_enabled = writes_enabled

    @classmethod
    def from_yaml(cls, path: str | Path, writes_enabled: bool = True) -> "PolicyEngine":
        return cls(yaml.safe_load(Path(path).read_text()), writes_enabled)

    def side_effect(self, tool: str) -> str:
        return self.tools[tool]["side_effect"]

    def in_scope(self, pr: Principal, res: ResourceContext) -> Decision | None:
        if res.tenant_id != pr.tenant_id:
            return Decision(Effect.DENY, "SC-01", "Resource belongs to another tenant")
        if res.bu_id and not pr.has_any_role(self.all_bu_roles) and res.bu_id not in pr.bu_ids:
            return Decision(Effect.DENY, "SC-02", "Resource belongs to a business unit outside the caller's scope")
        return None

    def decide(self, pr: Principal, tool: str, res: ResourceContext | None) -> Decision:
        spec = self.tools.get(tool)
        if spec is None:
            return Decision(Effect.DENY, "POL-00", f"Unknown tool {tool}")
        if pr.is_service_account:
            return Decision(Effect.DENY, "POL-SA", "Agent must act on behalf of an authenticated user")
        is_write = spec["side_effect"] != READ
        if spec.get("deny_all"):
            return Decision(Effect.DENY, spec["rule_id"], spec.get("reason", "Tool not permitted"))
        if is_write and not self.writes_enabled:
            return Decision(Effect.DENY, "KS-01", "Write actions are disabled (kill switch)")
        if res is not None and (d := self.in_scope(pr, res)):
            return d
        allowed = spec.get("allow_roles", self.read_roles if not is_write else ())
        if not pr.has_any_role(allowed):
            rid = spec.get("rule_id", "RD-01")
            return Decision(Effect.DENY, f"{rid}:ROLE", f"Role(s) {list(map(str, pr.roles))} may not use {tool}")
        if "no_active_holds" in spec.get("preconditions", []) and res is not None and (res.active_hold_count or 0) > 0:
            return Decision(Effect.DENY, f"{spec['rule_id']}:PRECONDITION", "Invoice has active holds")
        if is_write and spec.get("approval") == "required":
            return Decision(Effect.REQUIRE_APPROVAL, spec["rule_id"], "Approval required",
                            tuple(spec.get("approver_roles", ())))
        return Decision(Effect.ALLOW, spec.get("rule_id", "RD-01"), "Allowed")

    def validate_approver(self, tool: str, requester: Principal, approver: Principal) -> Decision:
        spec = self.tools[tool]
        if approver.tenant_id != requester.tenant_id:
            return Decision(Effect.DENY, "SOD-02", "Approver is in a different tenant")
        if approver.user_id == requester.user_id:
            return Decision(Effect.DENY, "SOD-01", "Approver must differ from requester (segregation of duties)")
        if not approver.has_any_role(spec.get("approver_roles", ())):
            return Decision(Effect.DENY, "SOD-03", "Approver lacks an approver role for this action")
        return Decision(Effect.ALLOW, spec["rule_id"], "Approver valid")
