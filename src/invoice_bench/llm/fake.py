"""Scripted chat model for deterministic graph/agent tests (no network, no tokens)."""
from __future__ import annotations

import json
from typing import Any, Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from pydantic import Field

Script = AIMessage | dict | str | Callable[[list[BaseMessage]], Any]


def _tok(s: str) -> int:
    return max(1, len(s) // 4)


class ScriptedChatModel(BaseChatModel):
    """Pops one scripted item per call. dict -> JSON content (for structured output); str -> text;
    AIMessage -> as-is (may carry tool_calls); callable(messages) -> any of the above."""

    script: list[Any] = Field(default_factory=list)
    calls: list[list[BaseMessage]] = Field(default_factory=list)
    bound_tools: list[Any] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _next(self, messages: list[BaseMessage]) -> AIMessage:
        self.calls.append(list(messages))
        if not self.script:
            raise RuntimeError("ScriptedChatModel: script exhausted")
        item = self.script.pop(0)
        if callable(item) and not isinstance(item, AIMessage):
            item = item(messages)
        if isinstance(item, dict):
            item = AIMessage(content=json.dumps(item))
        elif isinstance(item, str):
            item = AIMessage(content=item)
        prompt = "".join(str(m.content) for m in messages)
        if not item.usage_metadata:
            item.usage_metadata = {"input_tokens": _tok(prompt), "output_tokens": _tok(str(item.content)) + 5,
                                   "total_tokens": _tok(prompt) + _tok(str(item.content)) + 5}
        return item

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._next(messages))])

    def bind_tools(self, tools, **kwargs):
        self.bound_tools = list(tools)
        return self

    def with_structured_output(self, schema, include_raw: bool = False, **kwargs):
        def run(messages):
            raw = self.invoke(messages)
            try:
                parsed, err = schema.model_validate_json(raw.content), None
            except Exception as e:  # mirror LangChain include_raw contract
                parsed, err = None, e
            return {"raw": raw, "parsed": parsed, "parsing_error": err} if include_raw else parsed
        return RunnableLambda(run)


def heuristic_model(n: int = 400) -> ScriptedChatModel:
    """Offline dry-run model: exercises the whole pipeline without an API key. Its scores mean NOTHING about LLMs."""
    import re

    def respond(messages):
        sys = str(messages[0].content)
        human = str(messages[1].content) if len(messages) > 1 else ""
        if sys.startswith("Classify the latest request"):
            last = json.loads(human)["turns"][-1]
            low = last.lower()
            intent = {"intent": "invoice_status", "invoice_ids": re.findall(r"INV-\d{5}", last)}
            if m := re.search(r"\bV-\d{4}\b", last):
                intent.update(intent="open_ended", vendor_id=m.group(0))
            if "price variance" in low and not intent["invoice_ids"]:
                intent.update(intent="open_ended", hold_code="PRICE_VARIANCE")
            if m := re.search(r"\bSV-\d+\b", last):
                intent["vendor_invoice_no"] = m.group(0)
            for kw, act in (("release", "release_hold"), ("reject", "reject_invoice"), ("approve", "approve_for_payment"),
                            ("schedule", "approve_for_payment"), ("po reference", "update_po_reference"),
                            ("correct po", "update_po_reference"), ("should be po", "update_po_reference"),
                            ("point at po", "update_po_reference"), ("purchase order on invoice", "update_po_reference"),
                            ("typo in its po", "update_po_reference")):
                if kw in low:
                    intent.update(intent="perform_action", requested_action=act)
                    break
            if intent.get("requested_action") == "update_po_reference":
                pos = re.findall(r"PO-\d{5}", last)
                intent["action_po_id"] = pos[-1] if pos else None
            if not intent["invoice_ids"] and " it" in f" {low}":
                intent["refers_to_previous"] = True
            return intent
        if sys.startswith("You are an Accounts Payable assistant. Answer"):
            ev = json.loads(human)["evidence"]
            parts = []
            for e in ev.get("invoices", []):
                a = e["analysis"]
                s = f"{e['invoice']['invoice_id']} is {a['status'].replace('_', ' ').lower()}."
                for f in a["findings"]:
                    s += f" Hold: {f['message']}."
                if a["next_actions"]:
                    s += f" Next: {a['next_actions'][0]['description']}"
                parts.append(s)
            if "search" in ev:
                ag = ev["search"]["aggregates"]
                parts.append(f"{ag['on_hold_count']} invoices on hold, total {ag['total_on_hold']}: " +
                             ", ".join(f"{x['invoice_id']} ({', '.join(x['active_holds'])})" for x in ev["search"]["results"]))
            if ev.get("unavailable_systems"):
                parts.append("Unavailable: " + ", ".join(ev["unavailable_systems"]) + ".")
            return " ".join(parts) or "No data."
        return "Dry-run baseline response (no tool use)."

    return ScriptedChatModel(script=[respond] * n)
