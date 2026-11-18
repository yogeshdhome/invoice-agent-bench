"""Regenerate the article's charts and the approval-sequence diagram from scored results (no tokens).
python -m invoice_bench.bench.figures results/final/report/scores.jsonl docs/adjudication_v1.yaml results/final/figures"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import yaml

from .adjudicate import apply
from .stats import pass_hat_k, wilson

COL = {"baseline": "#9AA5B1", "ablation_a1": "#E3A857", "hardened": "#2F6FDE"}
LAB = {"baseline": "Baseline (B0)", "ablation_a1": "User-identity variant (A1)", "hardened": "Hardened (H)"}
AUTHZ = {"access_violation", "approval_write", "prompt_injection"}


def _rate(rs, key):
    k = sum(bool(r[key]) for r in rs)
    p, lo, hi = wilson(k, len(rs))
    return 100 * p, max(0, 100 * (p - lo)), max(0, 100 * (hi - p))


def charts(rows, A, out: Path, plt):
    excluded = [r for r in rows if r["scenario_id"] != "AP-009"]
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    for i, (key, src) in enumerate([("strict_success", excluded), ("strict_success_adj", A)]):
        for j, arm in enumerate(["baseline", "hardened"]):
            p, lo, hi = _rate([r for r in src if r["arm"] == arm], key)
            x = i * 2.6 + j
            ax.bar(x, p, color=COL[arm], yerr=[[lo], [hi]], capsize=3, label=LAB[arm] if i == 0 else None)
            ax.text(x, p + hi + 1.5, f"{p:.1f}%", ha="center", fontsize=9)
    ax.set_xticks([0.5, 3.1]); ax.set_xticklabels(["Frozen scorer (primary)", "Adjudicated (LLM-assisted,\nauthor-approved)"])
    ax.set_ylim(0, 118); ax.set_ylabel("Strict task success (%)"); ax.legend(frameon=False, loc="upper center", ncol=2)
    ax.set_title("Strict task success, 99 scenarios × 3 trials (95% CI)", fontsize=10)
    fig.tight_layout(); fig.savefig(out / "fig1_strict_success.png", dpi=200); plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.2, 3.4))
    for arm in ["baseline", "hardened"]:
        by = collections.defaultdict(list)
        for r in A:
            if r["arm"] == arm:
                by[r["scenario_id"]].append(r["strict_success_adj"])
        ys = [100 * pass_hat_k(by, k) for k in (1, 2, 3)]
        ax.plot([1, 2, 3], ys, marker="o", color=COL[arm], label=LAB[arm])
        for k, y in zip([1, 2, 3], ys):
            ax.text(k, y + 1.5, f"{y:.1f}", ha="center", fontsize=8)
    ax.set_xticks([1, 2, 3]); ax.set_xlabel("k (all k trials must succeed)"); ax.set_ylabel("pass^k (%)")
    ax.set_ylim(60, 102); ax.legend(frameon=False, loc="lower left"); ax.set_title("Consistency: pass^k (adjudicated)", fontsize=10)
    fig.tight_layout(); fig.savefig(out / "fig2_pass_k.png", dpi=200); plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    for j, arm in enumerate(["baseline", "ablation_a1", "hardened"]):
        rs = [r for r in A if r["arm"] == arm and r["category"] in AUTHZ]
        p, lo, hi = _rate(rs, "strict_success_adj")
        v = sum(bool(r["unauth_executed"] or r["disclosed"]) for r in rs)
        ax.bar(j, p, color=COL[arm], yerr=[[lo], [hi]], capsize=3)
        ax.text(j, p + hi + 1.5, f"{p:.1f}%", ha="center", fontsize=9)
        ax.text(j, 6, f"{v}/{len(rs)} runs\nretrieved out-of-scope\ndata", ha="center", fontsize=8,
                color="white" if arm != "ablation_a1" else "black")
    ax.set_xticks([0, 1, 2]); ax.set_xticklabels([LAB[a] for a in ["baseline", "ablation_a1", "hardened"]], fontsize=8.5)
    fz = {a: _rate([r for r in excluded if r["arm"] == a and r["category"] in AUTHZ], "strict_success")[0]
          for a in ["baseline", "ablation_a1", "hardened"]}
    ax.set_ylim(0, 112); ax.set_ylabel("Strict task success (%), adjudicated")
    ax.set_title("Authorization-sensitive scenarios (27 × 3 runs), adjudicated (LLM-assisted, author-approved)\n"
                 f"Frozen scorer: {fz['baseline']:.1f}% → {fz['ablation_a1']:.1f}% → {fz['hardened']:.1f}%", fontsize=9.5)
    fig.tight_layout(); fig.savefig(out / "fig3_authz_ablation.png", dpi=200); plt.close(fig)

    st = {}
    for arm in ["baseline", "hardened"]:
        rs = [r for r in rows if r["arm"] == arm]
        ra = [r for r in A if r["arm"] == arm]
        st[arm] = (sum(r["input_tokens"] + r["output_tokens"] for r in rs) / len(rs),
                   1000 * sum(r["cost"] for r in rs) / sum(r["strict_success_adj"] for r in ra))
    fig, axs = plt.subplots(1, 2, figsize=(6.4, 3.0))
    for ax, (i, t, u) in zip(axs, [(0, "Tokens per run\n(all 300 runs per arm)", "tokens"),
                                   (1, "Cost per successful task\n(all-run cost ÷ adjudicated successes)", "USD × 10⁻³")]):
        for j, arm in enumerate(["baseline", "hardened"]):
            v = st[arm][i]
            ax.bar(j, v, color=COL[arm]); ax.text(j, v * 1.02, f"{v:,.0f}" if i == 0 else f"{v:.2f}", ha="center", fontsize=9)
        ax.set_xticks([0, 1]); ax.set_xticklabels(["B0", "H"]); ax.set_title(t, fontsize=9); ax.set_ylabel(u)
    fig.tight_layout(); fig.savefig(out / "fig4_efficiency.png", dpi=200); plt.close(fig)


def approval_sequence(out: Path, plt):
    lanes = ["Requester", "Agent (graph)", "Policy engine", "Approver", "AP service"]
    X = {n: i * 2.2 for i, n in enumerate(lanes)}
    steps = [("Requester", "Agent (graph)", '1. "Release the hold on INV-10181"', 1),
             ("Agent (graph)", "AP service", "2. read invoice, PO, receipts (as the user)", 1),
             ("Agent (graph)", "Policy engine", "3. authorize(release_hold)", 1),
             ("Policy engine", "Agent (graph)", "4. REQUIRE_APPROVAL (rule AP-07)", 1),
             ("Agent (graph)", "Approver", "5. approval card: action hash + system evidence", 1),
             ("Approver", "Agent (graph)", "6. approve(action hash) — approver ID asserted, not authenticated", 1),
             ("Agent (graph)", "Agent (graph)", "7. check hash, expiry, approver ≠ requester", 1),
             ("Agent (graph)", "AP service", "8. re-check state, authority and reason", 0),
             ("Agent (graph)", "AP service", "9. release_hold + Idempotency-Key", 1),
             ("AP service", "Agent (graph)", "10. 200 (or idempotent replay)", 1),
             ("Agent (graph)", "AP service", "11. re-read invoice (postcondition)", 1),
             ("Agent (graph)", "Requester", '12. "Done" + audit reference', 1)]
    H = len(steps) * 0.62 + 1.2
    fig, ax = plt.subplots(figsize=(10.5, H * 0.95))
    top = H - 0.4
    for n, x in X.items():
        ax.add_patch(plt.Rectangle((x - 0.85, top - 0.1), 1.7, 0.5, facecolor="#DBE7FB" if n == "Agent (graph)" else "#EDF2F7",
                                   edgecolor="#4A5568"))
        ax.text(x, top + 0.15, n, ha="center", va="center", fontsize=10)
        ax.plot([x, x], [0.2, top - 0.1], color="#A0AEC0", lw=1, ls=(0, (3, 3)))
    y = top - 0.6
    for a, b, label, impl in steps:
        col = "#2F6FDE" if impl else "#C0392B"
        if a == b:
            x = X[a]
            ax.annotate("", xy=(x + 0.05, y - 0.22), xytext=(x + 0.05, y),
                        arrowprops=dict(arrowstyle="->", color=col, connectionstyle="arc3,rad=-1.2", lw=1.3))
            ax.text(x + 0.55, y - 0.1, label, fontsize=8.8, va="center")
        else:
            ax.annotate("", xy=(X[b], y), xytext=(X[a], y), arrowprops=dict(arrowstyle="->", color=col, lw=1.4, ls="-" if impl else "--"))
            ax.text((X[a] + X[b]) / 2, y + 0.09, label + ("" if impl else "   [recommended — not in benchmark]"), ha="center",
                    fontsize=8.8, color="#1A202C" if impl else "#C0392B")
        y -= 0.62
    ax.set_xlim(-1.2, X["AP service"] + 1.2); ax.set_ylim(0, H + 0.2); ax.axis("off")
    ax.set_title("Approval-required action: implemented (solid) and the recommended extra check (dashed)", fontsize=10.5)
    fig.tight_layout(); fig.savefig(out / "fig0c_approval_sequence.png", dpi=200); plt.close(fig)


def main() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    scores, adj, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(l) for l in scores.read_text().splitlines()]
    A = apply(rows, yaml.safe_load(adj.read_text()))
    charts(rows, A, out, plt)
    approval_sequence(out, plt)
    print(f"figures written to {out}")


if __name__ == "__main__":
    main()
