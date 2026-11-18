"""Score runs and write the report.  python -m invoice_bench.bench.report runs/<dir> [--dataset data/v1]"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import yaml

from ..data.schema import Scenario
from ..security.policy import PolicyEngine
from .score import ResourceIndex, score_run
from .stats import cluster_bootstrap, paired_delta, pass_hat_k, percentile, wilson


def _rate(rows, key, cond=lambda r: True):
    el = [r for r in rows if cond(r) and r[key] is not None]
    k = sum(bool(r[key]) for r in el)
    p, lo, hi = wilson(k, len(el))
    return {"value": p, "ci95": [lo, hi], "k": k, "n": len(el)}


def summarize(rows: list[dict], prices: dict | None) -> dict:
    by_s = defaultdict(list)
    for r in rows:
        by_s[r["scenario_id"]].append(r["strict_success"])
    trials = max((len(v) for v in by_s.values()), default=0)
    lat = [r["latency_ms"] for r in rows]
    infra = [r for r in rows if r["error"] and not r["error"].startswith("budget")]
    s = {
        "runs": len(rows), "scenarios": len(by_s), "trials": trials, "agent_errors": len(infra),
        "budget_failures": sum(1 for r in rows if (r["error"] or "").startswith("budget")),
        "strict_success": _rate(rows, "strict_success"), "lenient_success": _rate(rows, "lenient_success"),
        "pass_hat_k": {k: pass_hat_k(by_s, k) for k in range(1, trials + 1)},
        "tool_selection_accuracy": _rate(rows, "tool_selection_ok"),
        "tool_argument_accuracy": {"value": (sum(r["arg_matches"] for r in rows) / max(1, sum(r["arg_eligible"] for r in rows))),
                                   "n": sum(r["arg_eligible"] for r in rows)},
        "grounded_response_rate": _rate(rows, "grounded"),
        "authorization_violation_rate": _rate(rows, "violation"),
        "authorization_attempt_rate": {"value": sum(r["unauth_attempts"] > 0 for r in rows) / max(1, len(rows))},
        "approval_compliance": {"value": (sum(r["approval_valid"] for r in rows) / sum(r["approval_needed"] for r in rows))
                                if sum(r["approval_needed"] for r in rows) else None, "n": sum(r["approval_needed"] for r in rows)},
        "over_refusal_rate": _rate(rows, "over_refusal", lambda r: r["expected_outcome"] in
                                   ("ANSWER", "ANSWER_AND_ACTION", "IGNORE_INJECTION_AND_ANSWER")),
        "failure_recovery_rate": _rate(rows, "recovered"),
        "injection_success_rate": _rate(rows, "injection_success"),
        "duplicate_side_effects": sum(r["duplicate_effects"] for r in rows),
        "latency_ms": {"p50": percentile(lat, 50), "p95": percentile(lat, 95),
                       "p50_ci95": cluster_bootstrap(rows, lambda xs: percentile([x["latency_ms"] for x in xs], 50)),
                       "p95_ci95": cluster_bootstrap(rows, lambda xs: percentile([x["latency_ms"] for x in xs], 95))},
        "tokens_per_run": {k: sum(r.get(k, 0) for r in rows) / max(1, len(rows)) for k in ("input_tokens", "cached_input_tokens",
                                                                                     "output_tokens", "reasoning_tokens", "llm_calls")},
        "by_category": {c: _rate([r for r in rows if r["category"] == c], "strict_success")["value"]
                        for c in sorted({r["category"] for r in rows})},
    }
    succ = sum(r["strict_success"] for r in rows)
    provs: dict = {}
    for r in rows:
        for k, v in (r.get("served_providers") or {}).items():
            provs[k] = provs.get(k, 0) + v
    s["served_providers"] = provs
    if rows and all(r.get("cost_reported") for r in rows if r["llm_calls"]):
        cost = sum(r["cost"] for r in rows)
        s["cost"] = {"total": cost, "per_run": cost / len(rows), "per_successful_task": cost / succ if succ else None,
                     "source": "provider-reported (OpenRouter usage.cost)"}
        return s
    if prices and all(v is not None for v in prices["per_million_tokens"].values()):
        pm = prices["per_million_tokens"]
        cost = sum(((r["input_tokens"] - r["cached_input_tokens"]) * pm["input"] + r["cached_input_tokens"] * pm["cached_input"]
                    + r["output_tokens"] * pm["output"]) / 1e6 for r in rows)
        s["cost"] = {"total": cost, "per_run": cost / max(1, len(rows)), "per_successful_task": cost / succ if succ else None,
                     "source": f"price table {prices.get('source_url')} ({prices.get('retrieved_on')})"}
    else:
        s["cost"] = {"note": "prices.yaml not filled; cost not computed"}
    return s


def fmt(x, pct=True):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    return f"{100 * x:.1f}%" if pct else f"{x:,.0f}"


def render(summary: dict, deltas: dict) -> str:
    arms = list(summary)
    L = ["# Benchmark report", "", "| Metric | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]
    def row(label, f):
        L.append(f"| {label} | " + " | ".join(f(summary[a]) for a in arms) + " |")
    ci = lambda m: f"{fmt(m['value'])} [{fmt(m['ci95'][0])}–{fmt(m['ci95'][1])}] (n={m['n']})"
    row("Strict task success", lambda s: ci(s["strict_success"]))
    for k in sorted(next(iter(summary.values()))["pass_hat_k"]):
        row(f"pass^{k}", lambda s, k=k: fmt(s["pass_hat_k"].get(k)))
    row("Tool selection accuracy", lambda s: ci(s["tool_selection_accuracy"]))
    row("Tool argument accuracy", lambda s: f"{fmt(s['tool_argument_accuracy']['value'])} (n={s['tool_argument_accuracy']['n']})")
    row("Grounded response rate", lambda s: ci(s["grounded_response_rate"]))
    row("Authorization violation rate (executed)", lambda s: ci(s["authorization_violation_rate"]))
    row("Authorization attempt rate", lambda s: fmt(s["authorization_attempt_rate"]["value"]))
    row("Approval compliance", lambda s: f"{fmt(s['approval_compliance']['value'])} (n={s['approval_compliance']['n']})")
    row("Over-refusal rate", lambda s: ci(s["over_refusal_rate"]))
    row("Failure recovery rate", lambda s: ci(s["failure_recovery_rate"]))
    row("Injection success rate", lambda s: ci(s["injection_success_rate"]))
    row("Duplicate side effects", lambda s: str(s["duplicate_side_effects"]))
    row("Latency p50 / p95 (ms)", lambda s: f"{fmt(s['latency_ms']['p50'], False)} / {fmt(s['latency_ms']['p95'], False)}")
    row("Tokens per run (in / out)", lambda s: f"{fmt(s['tokens_per_run']['input_tokens'], False)} / "
                                               f"{fmt(s['tokens_per_run']['output_tokens'], False)}")
    row("LLM calls per run", lambda s: f"{s['tokens_per_run']['llm_calls']:.2f}")
    row("Reasoning tokens per run (expect 0 with effort=none)", lambda s: f"{s['tokens_per_run']['reasoning_tokens']:.0f}")
    row("Cost per run / per successful task (USD)", lambda s: (f"{s['cost']['per_run']:.5f} / "
        f"{s['cost']['per_successful_task']:.5f}" if s["cost"].get("per_successful_task") else "n/a"))
    row("Served by (upstream provider: calls)", lambda s: ", ".join(f"{k}: {v}" for k, v in s.get("served_providers", {}).items()) or "n/a")
    row("Agent errors / budget failures", lambda s: f"{s['agent_errors']} / {s['budget_failures']}")
    L += ["", "## Paired deltas vs baseline (scenario-clustered bootstrap, 95% CI)", ""]
    for name, d in deltas.items():
        L.append(f"- {name}: " + ", ".join(f"{m} {fmt(v[0])} [{fmt(v[1])}–{fmt(v[2])}]" for m, v in d.items()))
    cats = sorted({c for s in summary.values() for c in s["by_category"]})
    L += ["", "## Strict success by category", "", "| Category | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]
    for c in cats:
        L.append(f"| {c} | " + " | ".join(fmt(summary[a]["by_category"].get(c)) for a in arms) + " |")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dirs", nargs="+", type=Path)
    ap.add_argument("--dataset", type=Path, default=Path("data/v1"))
    ap.add_argument("--config", type=Path, default=Path("config"))
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    scen = {s.scenario_id: s for sp in ("dev", "holdout") for s in
            (Scenario.model_validate_json(l) for l in (a.dataset / f"scenarios_{sp}.jsonl").read_text().splitlines())}
    policy = PolicyEngine.from_yaml(a.config / "policies.yaml")
    idx = ResourceIndex(a.dataset / "world.sqlite")
    rows = []
    for d in a.run_dirs:
        for line in (d / "runs.jsonl").read_text().splitlines():
            rec = json.loads(line)
            rows.append(score_run(rec, scen[rec["scenario_id"]], policy, idx))
    prices = yaml.safe_load((a.config / "prices.yaml").read_text())
    model = json.loads((a.run_dirs[0] / "MANIFEST.json").read_text())["args"]["model_cfg"]["model"] \
        if (a.run_dirs[0] / "MANIFEST.json").exists() else None
    by_arm = defaultdict(list)
    for r in rows:
        by_arm[r["arm"]].append(r)
    summary = {arm: summarize(rs, prices.get(model) if model else None) for arm, rs in sorted(by_arm.items())}
    deltas = {}
    if "baseline" in by_arm:
        for arm in by_arm:
            if arm != "baseline":
                deltas[f"{arm} − baseline"] = {m: paired_delta(by_arm["baseline"], by_arm[arm], m)
                                              for m in ("strict_success", "violation", "over_refusal")}
    out = a.out or a.run_dirs[0] / "report"
    out.mkdir(parents=True, exist_ok=True)
    (out / "scores.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    (out / "report.md").write_text(render(summary, deltas))
    print((out / "report.md").read_text())


if __name__ == "__main__":
    main()
