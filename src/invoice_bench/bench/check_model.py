"""Pre-run model/route check.  python -m invoice_bench.bench.check_model [--no-calls]

Step 0 (ZERO tokens): ask OpenRouter which parameters the pinned upstream endpoint supports and compare with the
exact parameters each arm sends (captured from the real request builders). With require_parameters=true, any
unsupported parameter makes every request fail with "No endpoints found..." - exactly what happened in re-pilot 1.
Step 1 (~1-2k tokens, skipped if step 0 fails): plain call, structured output, tool call, cost/provider fields.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

import httpx
from langchain_core.messages import HumanMessage, SystemMessage

from ..agents.hardened.prompts import INTENT_SYSTEM, Intent
from ..llm.factory import get_chat_model, load_model_cfg
from ..tools.contracts import CONTRACTS


def request_params(cfg: dict) -> dict[str, set[str]]:
    """Top-level request parameters per call type (verified offline against langchain-openrouter 0.2.9)."""
    base = {"max_tokens"} | ({"temperature"} if cfg.get("temperature") is not None else set()) \
        | ({"reasoning"} if cfg.get("reasoning") is not None else set())
    so = {"response_format"} if cfg.get("structured_output_method") == "json_schema" else {"tools", "tool_choice"}
    return {"baseline_agent_step": base | {"tools"}, "hardened_intent": base | so, "hardened_explainer": base}


def endpoint_report(cfg: dict) -> tuple[bool, dict]:
    url = f"https://openrouter.ai/api/v1/models/{cfg['model']}/endpoints"
    headers = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"} if os.environ.get("OPENROUTER_API_KEY") else {}
    r = httpx.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    eps = (r.json().get("data") or {}).get("endpoints") or []
    pinned = [p.lower() for p in (cfg.get("openrouter_provider") or {}).get("order", [])]
    rows, ok = [], True
    for ep in eps:
        tag = str(ep.get("tag") or ep.get("provider_name") or "").lower()
        name = str(ep.get("provider_name") or tag)
        supported = set(ep.get("supported_parameters") or [])
        is_pinned = not pinned or any(tag.startswith(p) or name.lower().startswith(p) for p in pinned)
        missing = {k: sorted(v - supported) for k, v in request_params(cfg).items() if v - supported}
        rows.append({"provider": name, "tag": tag, "pinned": is_pinned, "status": ep.get("status"),
                     "supported_parameters": sorted(supported), "missing_for_our_calls": missing})
        if is_pinned and missing:
            ok = False
    if pinned and not any(r["pinned"] for r in rows):
        ok = False
        rows.append({"error": f"no endpoint matches pinned provider(s) {pinned}"})
    return ok, {"model": cfg["model"], "routing": cfg.get("openrouter_provider"), "endpoints": rows}


async def live_calls(cfg: dict) -> dict:
    m = get_chat_model(cfg)
    out: dict = {}
    r = await m.ainvoke([HumanMessage("Reply with the single word OK.")])
    out["plain_call"] = str(r.content)[:20]
    out["usage_metadata"] = r.usage_metadata
    out["served_provider"] = r.response_metadata.get("provider")
    out["cost_reported"] = r.response_metadata.get("cost")
    kw = {"method": cfg["structured_output_method"]} if cfg.get("structured_output_method") else {}
    s = await m.with_structured_output(Intent, include_raw=True, **kw).ainvoke(
        [SystemMessage(INTENT_SYSTEM), HumanMessage(json.dumps({"turns": ["Please release the hold on INV-10482."],
                                                                "previously_discussed_invoices": []}))])
    out["structured_output"] = s["parsed"].model_dump() if s["parsed"] else f"FAILED: {s['parsing_error']}"
    from langchain_core.tools import StructuredTool
    t = StructuredTool.from_function(func=lambda invoice_id: "{}", name="get_invoice", description=CONTRACTS["get_invoice"].description,
                                     args_schema=CONTRACTS["get_invoice"].args_model)
    tr = await m.bind_tools([t]).ainvoke([HumanMessage("Look up invoice INV-10482.")])
    out["tool_calling"] = [c["name"] for c in tr.tool_calls]
    return out


PROBE_EVIDENCE = {"question": "Check invoice INV-10482, explain why it is blocked, and tell me what needs to happen next.",
                  "evidence": {"invoices": [{"invoice": {"invoice_id": "INV-10482", "status": "ON_HOLD", "total": "2317.48",
                                                         "currency": "USD"},
                                             "analysis": {"status": "ON_HOLD", "active_holds": ["PRICE_VARIANCE"],
                                                          "findings": [{"code": "PRICE_VARIANCE", "message": "Unit price exceeds PO",
                                                                        "details": {"lines": [{"invoice_unit_price": "104.10",
                                                                                               "po_unit_price": "102.00",
                                                                                               "variance_pct": "2.06"}]}}],
                                                          "next_actions": [{"action": "REQUEST_PO_PRICE_AMENDMENT_OR_CREDIT_MEMO",
                                                                            "owner": "PROCUREMENT_BUYER"}]}}]}}


async def reasoning_probe(cfg: dict) -> list[dict]:
    """~3 small explainer-style calls: does the configured `reasoning` setting actually stop thinking tokens?"""
    from ..agents.hardened.prompts import COMPOSE_SYSTEM
    out = []
    for label, reasoning in (("as_configured", cfg.get("reasoning")), ("effort_none", {"effort": "none"}),
                             ("enabled_false", {"enabled": False})):
        m = get_chat_model({**cfg, "reasoning": reasoning})
        r = await m.ainvoke([SystemMessage(COMPOSE_SYSTEM), HumanMessage(json.dumps(PROBE_EVIDENCE))])
        um = r.usage_metadata or {}
        out.append({"setting": label, "reasoning": reasoning, "output_tokens": um.get("output_tokens"),
                    "reasoning_tokens": (um.get("output_token_details") or {}).get("reasoning", 0),
                    "cost": r.response_metadata.get("cost")})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-calls", action="store_true", help="only the zero-token endpoint check")
    ap.add_argument("--reasoning-probe", action="store_true", help="~3 explainer calls comparing reasoning settings")
    a = ap.parse_args()
    cfg = load_model_cfg()
    ok, rep = endpoint_report(cfg)
    print(json.dumps(rep, indent=2))
    pinned = [r for r in rep["endpoints"] if r.get("pinned")]
    summary = {"pinned_endpoints": [r["provider"] for r in pinned],
               "missing": sorted({p for r in pinned for v in r["missing_for_our_calls"].values() for p in v}),
               "supported_by_pinned": sorted(set().union(*(set(r["supported_parameters"]) for r in pinned))) if pinned else [],
               "errors": [r["error"] for r in rep["endpoints"] if "error" in r]}
    print("\nSUMMARY " + json.dumps(summary), file=sys.stderr)
    if not ok:
        print(f"FAIL: pinned endpoint(s) {summary['pinned_endpoints'] or 'NONE FOUND'} do not support: "
              f"{summary['missing'] or summary['errors']}. No tokens were spent.", file=sys.stderr)
        sys.exit(2)
    if a.no_calls:
        return
    if a.reasoning_probe:
        print(json.dumps(asyncio.run(reasoning_probe(cfg)), indent=2, default=str))
        return
    print(json.dumps(asyncio.run(live_calls(cfg)), indent=2, default=str))


if __name__ == "__main__":
    main()
