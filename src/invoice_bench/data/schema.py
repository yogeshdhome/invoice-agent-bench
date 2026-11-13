"""Scenario file schema (JSONL). See synthetic_data_plan.md §4."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["normal", "open_ended", "payment_status", "po_issue", "amount_mismatch", "duplicate",
                   "access_violation", "approval_write", "prompt_injection", "ambiguous", "tool_failure"]
Outcome = Literal["ANSWER", "ANSWER_AND_ACTION", "ACTION_NOT_APPROVED", "BLOCKED_UNAUTHORIZED", "CLARIFY",
                  "SAFE_FAILURE", "IGNORE_INJECTION_AND_ANSWER"]

PLAN_COUNTS: dict[str, int] = {"normal": 12, "open_ended": 3, "payment_status": 10, "po_issue": 10, "amount_mismatch": 14,
                               "duplicate": 8, "access_violation": 10, "approval_write": 10, "prompt_injection": 8,
                               "ambiguous": 6, "tool_failure": 9}
HOLDOUT_COUNTS: dict[str, int] = {"normal": 4, "open_ended": 1, "payment_status": 3, "po_issue": 3, "amount_mismatch": 4,
                                  "duplicate": 2, "access_violation": 3, "approval_write": 3, "prompt_injection": 2,
                                  "ambiguous": 2, "tool_failure": 3}


class Persona(BaseModel):
    user_id: str
    tenant_id: str
    roles: list[str]
    bu_ids: list[str]


class Turn(BaseModel):
    role: Literal["user"] = "user"
    content: str


class GroundTruth(BaseModel):
    expected_outcome: Outcome
    expected_status: str | None = None
    expected_root_causes: list[str] = Field(default_factory=list)
    expected_next_action: dict | None = None
    required_facts: dict[str, str] = Field(default_factory=dict)      # must appear: what the question actually asks
    supporting_facts: dict[str, str] = Field(default_factory=dict)    # may appear; never required (v1.1)
    forbidden_facts: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)       # must be CALLED (attempted); reads scored as superset
    forbidden_tools: list[str] = Field(default_factory=list)      # must NOT be EXECUTED
    required_args: dict[str, dict] = Field(default_factory=dict)
    expected_db_diff: list[dict] = Field(default_factory=list)
    approval_required: bool = False
    injection_goal: dict | None = None
    # v1.2: other outcomes that also count as correct, each with its own required mentions,
    # e.g. [{"outcome": "ANSWER", "required_mentions": ["INV-1", "INV-2"]}]
    accepted_alternatives: list[dict] = Field(default_factory=list)


class Scenario(BaseModel):
    scenario_id: str
    version: str = "1.2.0"
    split: Literal["dev", "holdout"]
    category: Category
    tags: list[str] = Field(default_factory=list)
    persona: Persona
    turns: list[Turn]
    fixtures: dict
    fault_plan: list[dict] = Field(default_factory=list)
    approver_script: dict | None = None
    ground_truth: GroundTruth
    generator: dict
