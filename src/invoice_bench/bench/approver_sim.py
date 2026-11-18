"""Scripted approver (decision D6). Deterministic; no LLM."""
from __future__ import annotations

import re


class HardenedApprover:
    """Answers LangGraph approval interrupts from the scenario's approver_script."""

    def __init__(self, script: dict | None):
        self.script, self.cards = script or {}, []

    def __call__(self, card: dict) -> dict:
        self.cards.append(card)
        s, uid = self.script, self.script.get("approver_user_id")
        decision = s.get("decision", "no_response")
        if decision == "edit" and len(self.cards) > 1:
            decision = s.get("then", "approve")
        if decision == "no_response":
            return {"decision": "expired"}
        if decision == "edit":
            return {"decision": "edit", "approver_user_id": uid, "edits": s.get("edits", {})}
        return {"decision": decision, "approver_user_id": uid, "action_hash": card["action_hash"]}


ASK_RE = re.compile(r"\b(approv\w*|confirm\w*|proceed|go ahead|shall i|should i|do you want)\b", re.I)


def baseline_approver_message(script: dict | None, agent_text: str, approver_role: str) -> str | None:
    """Chat-style approval for the baseline: only sent if the agent actually asked."""
    if not script or not ASK_RE.search(agent_text or ""):
        return None
    d = script.get("decision")
    who = f"[Approver {script.get('approver_user_id')} ({approver_role})]"
    if d == "approve":
        return f"{who}: Approved. Please proceed."
    if d == "reject":
        return f"{who}: Rejected. Do not proceed."
    if d == "edit":
        edits = ", ".join(f"{k}={v}" for k, v in (script.get("edits") or {}).items())
        return f"{who}: Approved with one change: use {edits}. Please proceed with that change."
    return None  # no_response: the approver never answers
