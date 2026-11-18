"""Render the dataset review pack for approval checkpoint #2.  python -m invoice_bench.data.review data/v1"""
from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

from ..services.db import connect


def main() -> None:
    d = Path(sys.argv[1] if len(sys.argv) > 1 else "data/v1")
    rows = [json.loads(l) for sp in ("dev", "holdout") for l in (d / f"scenarios_{sp}.jsonl").read_text().splitlines()]
    m = json.loads((d / "MANIFEST.json").read_text())
    rep = json.loads((d / "validation_report.json").read_text())
    conn = connect(d / "world.sqlite")
    L = ["# Dataset review pack — v1", "",
         f"Seed `{m['seed']}` · world dump SHA-256 `{m['world_dump_sha256'][:16]}…` · validator: **{'PASS' if rep['ok'] else 'FAIL'}** "
         f"({rep['pre_payment_invoices_checked']} pre-payment invoices re-checked against the rule engine)", "",
         "## World size", "", "| Table | Rows |", "|---|---:|"] + [f"| {k} | {v} |" for k, v in m["row_counts"].items()]
    L += ["", "## Distribution", "", "| Category | Dev | Holdout | Total |", "|---|---:|---:|---:|"]
    for cat, n in m["scenario_counts"].items():
        dv = sum(r["category"] == cat and r["split"] == "dev" for r in rows)
        L.append(f"| {cat} | {dv} | {n - dv} | {n} |")
    oc = Counter(r["ground_truth"]["expected_outcome"] for r in rows)
    tg = Counter(t for r in rows for t in r["tags"])
    L += ["", "**Expected outcomes:** " + ", ".join(f"{k} {v}" for k, v in sorted(oc.items())),
          "", "**Tags:** " + ", ".join(f"{k} {v}" for k, v in sorted(tg.items())), "",
          "## 20 random scenarios (seeded sample)", "", "| ID | Split | Persona | User message | Expected | Root causes | Key facts |",
          "|---|---|---|---|---|---|---|"]
    for r in sorted(random.Random(42).sample(rows, 20), key=lambda r: r["scenario_id"]):
        g = r["ground_truth"]
        msg = " ⏎ ".join(t["content"] for t in r["turns"]).replace("|", "/")
        facts = ", ".join(f"{k}={v}" for k, v in list(g["required_facts"].items())[:3]).replace("|", "/")
        L.append(f"| {r['scenario_id']} | {r['split']} | {r['persona']['roles'][0]} ({r['persona']['tenant_id']}) | {msg} | "
                 f"{g['expected_outcome']} | {', '.join(g['expected_root_causes']) or '—'} | {facts or '—'} |")
    L += ["", "## All injection payloads", ""]
    for r in sorted((r for r in rows if r["category"] == "prompt_injection"), key=lambda r: r["scenario_id"]):
        inv = conn.execute("SELECT vendor_memo, attachment_text FROM invoices WHERE invoice_id=?", [r["fixtures"]["primary_invoice"]]).fetchone()
        field = r["fixtures"]["injection_field"]
        text = inv["vendor_memo"] if field == "vendor_memo" else inv["attachment_text"]
        L += [f"### {r['scenario_id']} · {', '.join(t for t in r['tags'] if t != 'has_injection')} · persona {r['persona']['roles'][0]}",
              f"Field: `{field}` on {r['fixtures']['primary_invoice']} · goal: `{json.dumps(r['ground_truth']['injection_goal'])}`",
              "", "```text", text, "```", ""]
    out = d.parent.parent / "docs" / "design" / "dataset_review.md"  # v1.0.1: file moved (V-18)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n")
    print(out)


if __name__ == "__main__":
    main()
