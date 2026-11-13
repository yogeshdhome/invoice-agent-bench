import ast
import json
import shutil
import sqlite3
from pathlib import Path

from invoice_bench.data.generate import generate
from invoice_bench.data.validate import validate

SRC = Path(__file__).resolve().parents[2] / "src" / "invoice_bench"


def test_validator_passes(dataset):
    rep = validate(dataset)
    assert rep["ok"], rep["errors"][:5]
    assert rep["scenarios"] == 100


def test_generation_is_deterministic(dataset, tmp_path):
    m2 = generate(20261111, tmp_path / "again")
    m1 = json.loads((dataset / "MANIFEST.json").read_text())
    assert m1["world_dump_sha256"] == m2["world_dump_sha256"] and m1["files"] == m2["files"]


def test_different_seed_differs(dataset, tmp_path):
    m = generate(7, tmp_path / "s7")
    assert m["world_dump_sha256"] != json.loads((dataset / "MANIFEST.json").read_text())["world_dump_sha256"]


def test_validator_catches_corrupted_label(dataset, tmp_path):
    d = tmp_path / "bad"
    shutil.copytree(dataset, d)
    c = sqlite3.connect(d / "world.sqlite")
    c.execute("UPDATE holds SET code='QTY_VARIANCE' WHERE hold_id=(SELECT hold_id FROM holds WHERE invoice_id='INV-10482')")
    c.commit()
    rep = validate(d)
    assert not rep["ok"] and any("INV-10482" in e for e in rep["errors"])


def test_oracle_is_independent_of_rule_engine():
    tree = ast.parse((SRC / "data" / "oracle.py").read_text())
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | \
               {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m and ("domain" in m or "rules" in m or "next_action" in m) for m in imported)


def test_running_example_present(dataset):
    rows = [json.loads(l) for l in (dataset / "scenarios_dev.jsonl").read_text().splitlines()]
    mm1 = next(r for r in rows if r["scenario_id"] == "MM-001")
    assert mm1["turns"][0]["content"].startswith("Check invoice INV-10482, explain why it is blocked")
    assert mm1["ground_truth"]["required_facts"]["variance_pct"] == "2.06"


def test_holdout_uses_unseen_paraphrases(dataset):
    hold = [json.loads(l) for l in (dataset / "scenarios_holdout.jsonl").read_text().splitlines()]
    assert all(r["generator"].get("paraphrase", 3) >= 3 for r in hold)
