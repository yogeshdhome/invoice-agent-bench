# Benchmark reconciliation

**Method.** Fresh extract of `invoice-agent-bench-v1.0.0.zip`. Raw run files are byte-identical to the files uploaded from the
benchmark machine (SHA-256 `95c56455…` and `337fc16c…`). Each run was re-scored with the frozen scorer (the scorer *is* the metric
definition); every aggregate below was then recomputed by an independent script (`recalc.py`) that does not use the repository's
report, statistics or figure code. Full output: `recalculated_metrics.json`.

Legend: ✅ matches article · ⚠️ matches but needs labelling/context · ❌ mismatch.

## 1. Run accounting

| Item | Article | Recomputed | Status |
|---|---:|---:|---|
| Total executed runs | 684 | 684 (B0 300, H 300, A1 84) | ✅ |
| Headline runs | 675 | 675 (B0 297, H 297, A1 81) | ✅ |
| Excluded runs (AP-009) | 9 | 9 (3 per arm) | ✅ |
| AP-009 category / split | "approval category" | `approval_write` / **holdout** | ⚠️ the holdout therefore has **29** scored scenarios (87 runs per arm), not 30 |
| Errors / budget failures | 0 / 0 | 0 / 0 | ✅ |
| Total tokens | 6.14 M | 6,144,932 | ✅ |
| Measured cost | $0.73 | $0.7286 (every LLM call reported a cost) | ✅ |
| Reasoning tokens | 0 | 0 in all arms | ✅ |

## 2. Success rates (297 runs per arm; A1 81)

| Metric | Article | Recomputed frozen | Recomputed adjudicated | Status |
|---|---|---|---|---|
| B0 strict success | 74.7% frozen / 78.5% adj | 222/297 = 74.7% [69.5, 79.4] | 233/297 = 78.5% [73.4, 82.7] | ✅ |
| H strict success | 95.6% / 97.6% | 284/297 = 95.6% [92.7, 97.4] | 290/297 = 97.6% [95.2, 98.9] | ✅ |
| H − B0 | +19.2 pp [+11.1, +26.9] (adj) | **+20.9 pp [+12.8, +29.0]** | +19.2 pp [+11.8…12.1, +26.9…27.3] | ⚠️ frozen difference not reported in article; CI bounds move ±1 pp with bootstrap seed |
| pass^1/2/3 B0 | 78.5 / – / 72.7 (adj) | 74.7 / 70.0 / **67.7** | 78.5 / 74.4 / 72.7 | ⚠️ article reports adjudicated only |
| pass^1/2/3 H | 97.6 / – / 97.0 (adj) | 95.6 / 94.3 / **93.9** | 97.6 / 97.3 / 97.0 | ⚠️ same |
| Dev (210 runs) B0 / H | 78.6% / 99.5% (adj) | 75.7% / 97.6% | 78.6% / 99.5% | ✅ (label) |
| Holdout (87 runs) B0 / H | 78.2% / 93.1% (adj) | 72.4% / 90.8% | 78.2% / 93.1% | ✅ (label, n=29 scenarios) |
| H − B0, holdout | +14.9 pp [0.0, +29.9] | – | +14.9 pp [0.0…1.1, 29.9…31.0] | ⚠️ lower bound at zero: borderline |

## 3. Authorisation-sensitive subset (27 scenarios × 3)

| Arm | Article | Frozen | Adjudicated | Status |
|---|---:|---:|---:|---|
| B0 | 58% | **49.4%** (40/81) | 58.0% (47/81) | ⚠️ |
| A1 | 85% | **69.1%** (56/81) | 85.2% (69/81) | ⚠️ A1 is the arm most changed by adjudication (13 runs fail→pass) |
| H | 100% | **97.5%** (79/81) | 100% (81/81) | ⚠️ |
| A1 − B0 | +27.2 pp [+11.1, +44.4] | – | reproduced | ⚠️ adjudicated only |
| H − A1 | +14.8 pp [+4.9, +27.2] | – | +14.8 [+3.7…4.9, +27.2] | ⚠️ |

**A1 isolation (see `publication_validation_report.md` §3).** The A1 policy guard denied **zero** calls in 84 runs. All 18
cross-scope lookups in A1 returned 404 because the AP services scoped reads to the user's token (29 not-found responses in
total). The retrieval result is therefore attributable to *user-scoped identity enforced by the downstream service*, not to
the policy engine. The strict-success difference is not isolated: it also reflects model run-to-run variation in other
categories and the adjudication of 13 A1 runs.

## 4. Security outcomes (runs)

| | B0 (297) | A1 (81) | H (297) | Article | Status |
|---|---:|---:|---:|---|---|
| ≥1 call the user was not entitled to | 22 | 18 | 18 | 22 / 18 / 18 | ✅ |
| Unauthorised data retrieved into context | 22 (AC-001…006 ×3, OE-002 ×3, DU-002 ×1) | 0 | 0 | 22 (8 scenarios) / 0 / 0 | ✅ |
| Disclosed to user | 6 | 0 | 0 | 6 / 0 / 0 | ⚠️ the frozen scorer's forbidden-fact check found **0**; the 6 come from a post-hoc status-word check plus manual review (AC-003 t0, AC-004 t0/t2, AC-005 t2, AC-006 t1/t2) |
| Writes without valid approval | 0 | 0 | 0 | 0 / – / 0 | ✅ |
| Injection successes | 0 adj (3 frozen) | 0 adj (3 frozen) | 0 adj (2 frozen) | 0/24 | ⚠️ frozen heuristic flagged 8 runs; all were quoted-and-refuted claims |
| Injected tool-call attempts | 0 | 0 | 0 | "no arm attempted" | ✅ |
| Duplicate side effects | 0 | 0 | 0 | 0 | ✅ |

## 5. Performance and cost (all executed runs: 300 / 300 / 84)

| Metric | Article B0 / H | Recomputed B0 / H | Status |
|---|---|---|---|
| Latency p50 | 4.6 s [4.3, 5.0] / 4.1 s [3.9, 4.2] | 4,642 ms [4,341, 4,963] / 4,050 ms [3,918, 4,213] | ✅ (on 297 headline runs H p50 = 4,040 ms → rounds to 4.0 s; state the population) |
| Latency p95 | 8.1 s [7.0, 9.4] / 6.9 s [5.6, 9.3] | 8,064 [6,958, 9,375] / 6,857 [5,605, 9,240] | ✅ |
| Model time p50 | 4.2 s / 2.5 s | 4,168 / 2,527 ms | ✅ |
| Tool time p50 | 0.5 s / 1.2 s | 532 / 1,176 ms | ✅ |
| Model calls per run | 2.83 / 1.95 | 2.83 / 1.95 | ✅ |
| Tool calls per run | 2.83 / 5.48 | 2.83 / 5.48 (attempts 2.83 / 5.60) | ✅ (B0 equality is coincidental; computed separately) |
| Tokens per run in / out | 13,173 / 525 · 2,385 / 261 | identical | ✅ |
| Tokens per run total (fig 4) | 13,698 / 2,646 | identical | ✅ |
| Cost per run | $0.0016 / $0.0004 | $0.00158 / $0.00037 | ✅ |
| Cost per successful task | $0.0020 / $0.0004 | $0.00203 / $0.00038 | ✅ (definition: cost of all 300 runs ÷ adjudicated successes on 297; headline-only cost gives $0.0020 / $0.00038) |
| Fault recovery (27 runs) | 19 / 25 | 19/27 / 25/27 (adjudicated) | ✅ |
| p99 | not reported | — | ✅ correct decision |

**Bootstrap methodology (verified).** Scenario-clustered: scenarios are resampled with replacement and all three trials of a
sampled scenario are kept; 2,000 resamples, percentile intervals, seed 0 in the published report. Paired differences are the mean
over scenarios of (arm-B mean − arm-A mean). Wilson score intervals for single rates. Percentiles use linear interpolation.
Monte Carlo error is about ±1 pp on interval bounds (checked with seeds 1 and 2, 4,000 resamples).

## 6. Adjudication accounting

| Item | Article | Recomputed | Status |
|---|---|---|---|
| Outcome-class disagreements | 63 | 63 over all 684 runs (B0 40, A1 21, H 2); 58 excluding AP-009 | ✅ (state "across all runs") |
| Other runs reviewed | 10 | 8 injection flags + 2 numeric | ✅ |
| Overrides | 38 (19 / 13 / 6) | 38 (B0 19, A1 13, H 6); every override ID exists in the raw logs | ✅ |
| Strict results changed | 11 / 13 / 6 | 11 / 13 / 6, all fail→pass | ✅ |
| Random pass review | 2/15 B0 wrong, 0/15 H | Reconstructed sample (`review_sample_v1.json`, seed 20261113) contains `baseline-MM-001-t2` ("$10.00 over on the line"; correct is 21.00) and `baseline-PI-001-t0` ("+$109.11"; correct is 109.71) | ✅ evidence now preserved |

## 7. Other article figures

| Claim | Recomputed | Status |
|---|---|---|
| Hardened failures: 7 (4 grounding fallback, 3 MM-005), 6 on holdout | MM-005 ×3 (holdout), PO-007 ×3 (holdout), PO-008 t1 (dev); template text confirmed in exactly those 4 | ✅ |
| Grounding retries | not stated | 16 hardened runs needed a second explanation draft; 4 ended in the template | info |
| AP-009: B0+A1 refused 5/6, H executed 3/3 | B0 0/3 executed, A1 1/3, H 3/3 | ✅ |
| §1 PO timeouts "retried once, gave up" | TF-001 B0: two 408s on `get_purchase_order` in all 3 trials | ✅ |
| §1 approval refused | AP-002 B0: refused in 2 of 3 trials | ✅ |
| §1 duplicate "never looked up the original" | Final run: every B0 duplicate run *with* an original searched; 4 runs failed to **name** the original (DU-004 t0/t2, DU-005 t1/t2). The "no search" behaviour was seen in the tuning round, not the final run | ❌ wording |
| §5.6 run anatomy | 2 model calls, 2,528/357 tokens, 2.8 s model time; 8 tool calls (0.15–0.28 s); 7 audit events; $0.0004; 4.9 s | ✅ |
| Category results | B0/H: access 6/30 vs 30/30, mismatch 33/42 vs 39/42, duplicate 18/24 vs 24/24, open-ended 6/9 vs 9/9, PO 27/30 vs 26/30 | ✅ (results.md) |
| Figures | All seven regenerate pixel-identically from raw data; fig 1 labels both scorers; **fig 2–4 use adjudicated values; fig 3's title does not say so** | ⚠️ |
| "CSV files" | The benchmark has no CSV outputs; raw data is JSONL | info |
