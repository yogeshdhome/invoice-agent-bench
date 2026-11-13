"""The published raw runs must reproduce the numbers in the article (offline, no tokens)."""
import json
from pathlib import Path

import pytest
import yaml

from invoice_bench.bench.adjudicate import apply, strict
from invoice_bench.bench.score import ResourceIndex, score_run
from invoice_bench.data.schema import Scenario
from invoice_bench.security.policy import PolicyEngine

ROOT = Path(__file__).resolve().parents[2]
FINAL = ROOT / "results" / "final"
pytestmark = pytest.mark.skipif(not (FINAL / "baseline_hardened" / "runs.jsonl").exists(), reason="published runs not present")


@pytest.fixture(scope="module")
def scored():
    data = ROOT / "data" / "v1"
    scen = {s.scenario_id: s for sp in ("dev", "holdout")
            for s in (Scenario.model_validate_json(l) for l in (data / f"scenarios_{sp}.jsonl").read_text().splitlines())}
    pol, idx = PolicyEngine.from_yaml(ROOT / "config" / "policies.yaml"), ResourceIndex(data / "world.sqlite")
    rows = []
    for d in ("baseline_hardened", "ablation_a1"):
        for line in (FINAL / d / "runs.jsonl").read_text().splitlines():
            r = json.loads(line)
            rows.append(score_run(r, scen[r["scenario_id"]], pol, idx))
    return rows


def test_run_accounting(scored):
    assert len(scored) == 684
    assert sum(r["scenario_id"] == "AP-009" for r in scored) == 9
    assert sum(r["input_tokens"] + r["output_tokens"] for r in scored) == 6_144_932


def test_frozen_scorer_headline(scored):
    def n(arm):
        return sum(r["strict_success"] for r in scored if r["arm"] == arm and r["scenario_id"] != "AP-009")
    assert (n("baseline"), n("hardened")) == (222, 284)          # 74.7% / 95.6% of 297


def test_adjudicated_headline(scored):
    adj = yaml.safe_load((ROOT / "docs" / "adjudication_v1.yaml").read_text())
    assert all(strict(r) == r["strict_success"] for r in scored)
    A = apply(scored, adj)
    got = {a: sum(r["strict_success_adj"] for r in A if r["arm"] == a) for a in ("baseline", "hardened", "ablation_a1")}
    assert got == {"baseline": 233, "hardened": 290, "ablation_a1": 69}   # 78.5% / 97.6% / 85.2%


def test_unauthorised_retrieval_counts(scored):
    ex = [r for r in scored if r["scenario_id"] != "AP-009"]
    retrieved = {a: sum(r["unauth_executed"] > 0 for r in ex if r["arm"] == a) for a in ("baseline", "hardened", "ablation_a1")}
    assert retrieved == {"baseline": 22, "hardened": 0, "ablation_a1": 0}
