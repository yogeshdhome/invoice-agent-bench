"""Benchmark runner.  python -m invoice_bench.bench.run --arm hardened --split dev --trials 3 [--fake]"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import time
import traceback
import uuid
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.types import Command

from ..agents.baseline.agent import build_baseline, final_text
from ..agents.hardened.graph import HardenedDeps, build_hardened
from ..data.schema import Scenario
from ..domain.rules import Tolerance
from ..llm.usage import BudgetCallback, BudgetExceeded
from ..observability.audit import AuditLog
from ..observability.tracing import RunTracer
from ..security.auth import SERVICE_PRINCIPAL, Principal, issue_token
from ..security.policy import PolicyEngine
from ..services.app import create_app
from ..services.db import connect
from ..services.faults import FaultController, LatencyModel
from ..services.repository import users_from_db
from ..tools.client import ServiceClient
from ..tools.policy_guard import PolicyGuardClient
from ..tools.resilient import ResilientClient, RetryPolicy
from .approver_sim import HardenedApprover, baseline_approver_message
from .snapshot import diff, snapshot

ARMS = ("baseline", "hardened", "ablation_a1")
TODAY = "2026-11-02"


@dataclass
class RunSettings:
    dataset: Path
    out: Path
    config_dir: Path = Path("config")
    latency: bool = True
    fault_delay_s: float = 5.0
    client_timeout_s: float = 2.0
    backoff_initial_s: float = 0.2
    structured_kwargs: dict = None

    def __post_init__(self):
        self.structured_kwargs = self.structured_kwargs or {}


def load_scenarios(dataset: Path, split: str) -> list[Scenario]:
    splits = ["dev", "holdout"] if split == "all" else [split]
    return [Scenario.model_validate_json(l) for s in splits for l in (dataset / f"scenarios_{s}.jsonl").read_text().splitlines()]


async def run_one(sc: Scenario, arm: str, trial: int, model, st: RunSettings, global_remaining: list[int] | None = None) -> dict:
    run_id = f"{arm}-{sc.scenario_id}-t{trial}-{uuid.uuid4().hex[:6]}"
    work = st.out / "work" / run_id
    work.mkdir(parents=True)
    db = work / "world.sqlite"
    shutil.copy(st.dataset / "world.sqlite", db)  # fresh world per scenario-trial
    before = snapshot(db)
    settings = yaml.safe_load((st.config_dir / "settings.yaml").read_text())
    policy = PolicyEngine.from_yaml(st.config_dir / "policies.yaml", settings.get("writes_enabled", True))
    faults = FaultController()
    faults.reset([{**f, "delay_s": st.fault_delay_s} for f in sc.fault_plan])
    lat = None
    if st.latency:
        prof = yaml.safe_load((st.config_dir / "latency_profile.yaml").read_text())
        lat = LatencyModel(prof["tools"], seed=zlib.crc32(f"{prof['seed']}:{sc.scenario_id}:{trial}".encode()))
    app = create_app(str(db), faults=faults, latency=lat, today=TODAY)
    transport = httpx.ASGITransport(app=app)
    tracer = RunTracer(st.out / "traces" / f"{run_id}.jsonl")
    persona = Principal(user_id=sc.persona.user_id, tenant_id=sc.persona.tenant_id, bu_ids=tuple(sc.persona.bu_ids),
                        roles=tuple(sc.persona.roles))
    b = settings["budgets"]["hardened" if arm == "hardened" else "baseline"]
    cb = BudgetCallback(b["max_llm_calls"], b["max_input_tokens_per_run"], global_remaining, tracer)
    config = {"configurable": {"thread_id": run_id, "principal": persona.model_dump(mode="json"), "bench_run_id": run_id},
              "callbacks": [cb], "recursion_limit": 2 * b["max_llm_calls"] + 25}
    events: list[dict] = []
    final, error, self_outcome = "", None, None
    audit = AuditLog(work / "audit.sqlite")
    inner = None
    t0 = time.perf_counter()
    with tracer.agent_run(arm, run_id):
        try:
            if arm == "hardened":
                inner = ServiceClient(transport, issue_token(persona), timeout_s=st.client_timeout_s, tracer=tracer)
                client = ResilientClient(inner, RetryPolicy(max_attempts=settings["tools"]["max_attempts"],
                                                            backoff_initial_s=st.backoff_initial_s))
                conn = connect(db)
                deps = HardenedDeps(model=model, client=client, policy=policy, directory=users_from_db(conn), audit=audit,
                                    tolerance=Tolerance.from_yaml(st.config_dir / "tolerances.yaml"),
                                    structured_kwargs=st.structured_kwargs)
                conn.close()
                graph = build_hardened(deps, InMemorySaver())
                approver = HardenedApprover(sc.approver_script)
                for turn in sc.turns:
                    res = await graph.ainvoke({"new_turn": turn.content}, config, durability="sync")
                    while res.get("__interrupt__"):
                        card = res["__interrupt__"][0].value
                        resume = approver(card)
                        events.append({"type": "approval_card", "card": card, "resume": resume, "seq": len(inner.records)})
                        res = await graph.ainvoke(Command(resume=resume), config, durability="sync")
                final, self_outcome = res.get("final", ""), res.get("outcome")
                records = inner.records
            else:
                token = issue_token(SERVICE_PRINCIPAL if arm == "baseline" else persona)
                inner = ServiceClient(transport, token, timeout_s=st.client_timeout_s, tracer=tracer)
                client = inner if arm == "baseline" else PolicyGuardClient(inner, policy, persona)
                agent = build_baseline(model, client, persona, InMemorySaver())
                state = {}
                for turn in sc.turns:
                    state = await agent.ainvoke({"messages": [HumanMessage(turn.content)]}, config)
                final = final_text(state)
                if sc.approver_script and not any(r.executed for r in inner.records):
                    approver_id = sc.approver_script["approver_user_id"]
                    conn = connect(db)
                    role = str(users_from_db(conn)[approver_id].roles[0])
                    conn.close()
                    msg = baseline_approver_message(sc.approver_script, final, role)
                    if msg:
                        events.append({"type": "chat_approval", "decision": sc.approver_script["decision"], "message": msg,
                                       "edits": sc.approver_script.get("edits"), "seq": len(inner.records)})
                        state = await agent.ainvoke({"messages": [HumanMessage(msg)]}, config)
                        final = final_text(state)
                records = inner.records
        except (BudgetExceeded, GraphRecursionError) as e:
            error, records = f"budget: {e}", inner.records if "inner" in dir() else []
        except Exception as e:  # recorded, never silently dropped (EVAL-11)
            error, records = f"exception: {type(e).__name__}: {e}", inner.records if "inner" in dir() else []
            (work / "traceback.txt").write_text(traceback.format_exc())
    e2e_ms = (time.perf_counter() - t0) * 1000
    after = snapshot(db)
    rec = {"run_id": run_id, "arm": arm, "scenario_id": sc.scenario_id, "trial": trial, "split": sc.split, "category": sc.category,
           "final_text": final, "self_reported_outcome": self_outcome, "error": error, "tool_calls": [r.as_dict() for r in records],
           "events": events, "db_diff": diff(before, after), "audit_events": len(audit.events()),
           "usage": {"llm_calls": cb.usage.llm_calls, "input_tokens": cb.usage.input_tokens, "cached_input_tokens":
                     cb.usage.cached_input_tokens, "output_tokens": cb.usage.output_tokens,
                     "reasoning_tokens": cb.usage.reasoning_tokens, "cost": round(cb.usage.cost, 8),
                     "cost_reported_calls": cb.usage.cost_reported_calls, "served_providers": cb.usage.served_providers,
                     "llm_ms": round(cb.usage.llm_ms, 1)},
           "latency_ms": round(e2e_ms, 1), "tool_ms": round(sum(r.latency_ms for r in records), 1),
           "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (work / "world.sqlite").unlink()
    return rec


def manifest(st: RunSettings, args: dict) -> dict:
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or None
    except Exception:
        sha = None
    return {"args": args, "git_sha": sha, "dataset_manifest": json.loads((st.dataset / "MANIFEST.json").read_text()),
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


class InfraAbort(RuntimeError):
    pass


async def run_batch(scenarios, arms, trials, model_for, st: RunSettings, token_budget: int | None, concurrency: int = 1,
                    max_consecutive_errors: int = 3, append: bool = False):
    st.out.mkdir(parents=True, exist_ok=True)
    if (st.out / "runs.jsonl").exists() and not append:
        raise SystemExit(f"{st.out / 'runs.jsonl'} already exists; use a new --out (or --append on purpose)")
    streak = [0]
    remaining = [token_budget] if token_budget else None
    sem = asyncio.Semaphore(concurrency)
    out_path = st.out / "runs.jsonl"
    jobs = [(sc, arm, t) for t in range(trials) for sc in scenarios for arm in arms]  # arms interleaved
    results = []

    async def go(sc, arm, t):
        async with sem:
            if remaining is not None and remaining[0] <= 0:
                return
            if streak[0] >= max_consecutive_errors:
                return  # infra abort: stop spending, keep what we have
            rec = await run_one(sc, arm, t, model_for(arm, t), st, remaining)
            failed_before_llm = (rec["error"] or "").startswith("exception") and rec["usage"]["llm_calls"] == 0
            streak[0] = streak[0] + 1 if failed_before_llm else 0
            with out_path.open("a") as f:
                f.write(json.dumps(rec) + "\n")
            results.append(rec)

    await asyncio.gather(*(go(*j) for j in jobs))
    if streak[0] >= max_consecutive_errors:
        print(f"INFRA ABORT after {streak[0]} consecutive runs failed before any LLM call. Last error: "
              f"{results[-1]['error'] if results else 'n/a'}. Run `make check-model`.")
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=ARMS + ("all", "bh"), default="bh")
    ap.add_argument("--split", choices=["dev", "holdout", "all"], default="dev")
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--scenarios", default="", help="comma-separated IDs")
    ap.add_argument("--dataset", type=Path, default=Path("data/v1"))
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--model", default="m2")
    ap.add_argument("--token-budget", type=int, default=None)
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--no-latency", action="store_true")
    ap.add_argument("--replay", action="store_true", help="read-only LLM cache (zero-cost replay of a previous run)")
    ap.add_argument("--categories", default="", help="comma-separated categories")
    ap.add_argument("--pilot", action="store_true", help="first dev scenario of each category (11)")
    ap.add_argument("--tune-subset", action="store_true",
                    help="stratified tuning set: next 2 dev scenarios per category after the pilot ones (~21)")
    ap.add_argument("--append", action="store_true", help="allow appending to an existing runs.jsonl")
    ap.add_argument("--max-consecutive-errors", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true", help="offline heuristic model; validates the pipeline, scores are meaningless")
    a = ap.parse_args()
    import os
    from ..llm.cache import SQLiteLLMCache
    from ..llm.factory import get_chat_model, load_model_cfg
    scenarios = load_scenarios(a.dataset, a.split)
    if a.scenarios:
        keep = set(a.scenarios.split(","))
        scenarios = [s for s in scenarios if s.scenario_id in keep]
    if a.categories:
        cats = set(a.categories.split(","))
        scenarios = [s for s in scenarios if s.category in cats]
    if a.tune_subset:
        taken: dict[str, int] = {}
        keep = []
        for s in [x for x in scenarios if x.split == "dev"]:
            n = taken.get(s.category, 0)
            taken[s.category] = n + 1
            if 1 <= n <= 2:  # skip index 0 (used by the pilot), take the next two
                keep.append(s)
        scenarios = keep
    if a.pilot:
        seen = set()
        scenarios = [s for s in scenarios if s.split == "dev" and not (s.category in seen or seen.add(s.category))]
    if a.limit:
        scenarios = scenarios[: a.limit]
    arms = ARMS if a.arm == "all" else (("baseline", "hardened") if a.arm == "bh" else (a.arm,))
    out = a.out or Path("runs") / datetime.now().strftime("%Y%m%d-%H%M%S")
    cfg = load_model_cfg(a.model)
    st = RunSettings(a.dataset, out, latency=not a.no_latency,
                     structured_kwargs={"method": cfg["structured_output_method"]} if cfg.get("structured_output_method") else {})
    cache_dir = out / "llm_cache"
    models = {}

    def model_for(arm, trial):
        if a.dry_run:
            from ..llm.fake import heuristic_model
            return heuristic_model()
        if (arm, trial) not in models:  # one cache per arm x trial index: trials are never collapsed
            models[(arm, trial)] = get_chat_model(cfg, cache=SQLiteLLMCache(cache_dir / f"{arm}_t{trial}.sqlite", read_only=a.replay))
        return models[(arm, trial)]

    budget = a.token_budget or int(os.environ.get("TOKEN_BUDGET_TOTAL", "0")) or None
    if (out / "runs.jsonl").exists() and not a.append:
        raise SystemExit(f"{out / 'runs.jsonl'} already exists; use a new --out (or --append on purpose)")
    out.mkdir(parents=True, exist_ok=True)
    (out / "MANIFEST.json").write_text(json.dumps(manifest(st, {**vars(a), "dataset": str(a.dataset), "out": str(out),
                                                                "model_cfg": cfg}), indent=2, default=str))
    res = asyncio.run(run_batch(scenarios, arms, a.trials, model_for, st, budget, a.concurrency,
                                a.max_consecutive_errors, a.append))
    toks = sum(r["usage"]["input_tokens"] + r["usage"]["output_tokens"] for r in res)
    print(json.dumps({"runs": len(res), "errors": sum(1 for r in res if r["error"]), "tokens": toks, "out": str(out)}, indent=2))


if __name__ == "__main__":
    main()
