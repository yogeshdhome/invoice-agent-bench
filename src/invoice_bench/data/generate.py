"""Generate the synthetic world DB + 100 scenarios.  python -m invoice_bench.data.generate --seed 20261111 --out data/v1"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
from pathlib import Path

from ..services.db import canonical_dump_sha256, connect, create_schema
from .schema import HOLDOUT_COUNTS, PLAN_COUNTS
from .templates import Factory
from .world import World

GENERATOR_VERSION = "1.2.0"  # 1.1: supporting_facts; 1.2: accepted_alternatives for read-only vendor-number ambiguity
ORDER = list(PLAN_COUNTS)


def assign_splits(seed: int) -> dict[str, list[str]]:
    rng = random.Random(seed + 1)
    out = {}
    for cat in ORDER:
        n, h = PLAN_COUNTS[cat], HOLDOUT_COUNTS[cat]
        pool = list(range(1, n)) if cat == "amount_mismatch" else list(range(n))  # MM-001 (running example) stays in dev
        hold = set(rng.sample(pool, h))
        out[cat] = ["holdout" if i in hold else "dev" for i in range(n)]
    return out


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def generate(seed: int, out: Path) -> dict:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    db_path = out / "world.sqlite"
    conn = connect(db_path)
    create_schema(conn)
    conn.execute("BEGIN")
    w = World(conn, random.Random(seed))
    w.build_master()
    w.build_background()
    f = Factory(w)
    splits = assign_splits(seed)
    for cat in ORDER:
        getattr(f, cat)(splits[cat])
    conn.execute("COMMIT")
    dump_hash = canonical_dump_sha256(conn)
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in
              ["tenants", "business_units", "users", "vendors", "purchase_orders", "po_lines", "goods_receipts", "gr_lines",
               "invoices", "invoice_lines", "holds", "payments"]}
    conn.close()
    scen = sorted(f.out, key=lambda s: s["scenario_id"])
    files = {}
    for split in ("dev", "holdout"):
        p = out / f"scenarios_{split}.jsonl"
        p.write_bytes("".join(json.dumps(s, sort_keys=True) + "\n" for s in scen if s["split"] == split).encode())  # LF on every OS
        files[p.name] = sha256_file(p)
    manifest = {"generator_version": GENERATOR_VERSION, "seed": seed, "world_dump_sha256": dump_hash, "files": files,
                "row_counts": counts, "scenario_counts": {c: sum(1 for s in scen if s["category"] == c) for c in ORDER},
                "split_counts": {sp: sum(1 for s in scen if s["split"] == sp) for sp in ("dev", "holdout")}}
    (out / "MANIFEST.json").write_bytes((json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261111)
    ap.add_argument("--out", type=Path, default=Path("data/v1"))
    m = generate(ap.parse_args().seed, ap.parse_args().out)
    print(json.dumps({k: m[k] for k in ("seed", "world_dump_sha256", "scenario_counts", "split_counts")}, indent=2))


if __name__ == "__main__":
    main()
