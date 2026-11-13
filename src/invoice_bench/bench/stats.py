"""Statistics: Wilson CIs, unbiased pass^k, scenario-clustered bootstrap (trials are not independent)."""
from __future__ import annotations

import math
import random
from collections import defaultdict


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return (float("nan"),) * 3
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, c - h), min(1.0, c + h)


def pass_hat_k(successes_by_scenario: dict[str, list[bool]], k: int) -> float:
    """tau-bench estimator: mean over tasks of C(c,k)/C(n,k)."""
    vals = []
    for trials in successes_by_scenario.values():
        n, c = len(trials), sum(trials)
        if n >= k:
            vals.append(math.comb(c, k) / math.comb(n, k))
    return sum(vals) / len(vals) if vals else float("nan")


def percentile(xs: list[float], q: float) -> float:
    if not xs:
        return float("nan")
    xs = sorted(xs)
    pos = (len(xs) - 1) * q / 100  # numpy "linear"
    lo, hi = math.floor(pos), math.ceil(pos)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def cluster_bootstrap(rows: list[dict], stat, key: str = "scenario_id", n: int = 2000, seed: int = 0) -> tuple[float, float]:
    by = defaultdict(list)
    for r in rows:
        by[r[key]].append(r)
    ids = sorted(by)
    rng = random.Random(seed)
    vals = []
    for _ in range(n):
        sample = [r for i in (rng.choice(ids) for _ in ids) for r in by[i]]
        v = stat(sample)
        if not math.isnan(v):
            vals.append(v)
    return (percentile(vals, 2.5), percentile(vals, 97.5)) if vals else (float("nan"), float("nan"))


def paired_delta(a: list[dict], b: list[dict], metric: str, n: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """Delta of mean(metric) B - A, paired by scenario, cluster bootstrap CI."""
    ma, mb = defaultdict(list), defaultdict(list)
    for r in a:
        ma[r["scenario_id"]].append(float(bool(r[metric])))
    for r in b:
        mb[r["scenario_id"]].append(float(bool(r[metric])))
    ids = sorted(set(ma) & set(mb))
    if not ids:
        return (float("nan"),) * 3

    def d(sel):
        return sum(sum(mb[i]) / len(mb[i]) - sum(ma[i]) / len(ma[i]) for i in sel) / len(sel)
    rng = random.Random(seed)
    boots = [d([rng.choice(ids) for _ in ids]) for _ in range(n)]
    return d(ids), percentile(boots, 2.5), percentile(boots, 97.5)
