# Changelog

## v1.0.1 — 2026-11-17 (post-validation; benchmark not re-run)

The published results (`results/final/`) were produced by v1.0.0 / `freeze-v1` and are unchanged. v1.0.1 fixes issues found
in the publication validation; none changes how the published runs are scored.

- **Hardened approval IDs bound to the request (V-14).** The approval ID and idempotency key now include a per-request nonce
  (thread + turn). In v1.0.0 a repeated identical request re-used the first request's approval row and expiry, and a later
  legitimate repeat would have replayed the old result. Not triggered in the benchmark (fresh database per run, one request per
  thread). Regression test: `test_repeated_request_gets_a_fresh_approval_not_the_expired_one`.
- **New tests (V-13, V-15):** concurrent same-key writes collapse to one effect (and different keys do not); time-based approval
  expiry; circuit breaker opens after five failed calls; audit log is append-only.
- **Figures:** fig 3 and fig 4 state that they use adjudicated values and show their populations; fig 0c notes that the approver
  identity is asserted, not authenticated.
- **Docs:** README and `docs/results.md` wording corrected (frozen results primary; A1 attribution; approver identity);
  `docs/review_sample_v1.md` preserves the random review sample and the six disclosure runs.
- **Fix:** `make reproduce-data` now writes the dataset review to `docs/design/` (V-18).
- **Scorer output made deterministic:** `unsupported_claims` is now sorted. Its order previously varied between runs (Python set
  order), so regenerated `scores.jsonl` files were not byte-identical. No value or metric changes (all 684 rows verified).
- **Terminology:** adjudication is described as LLM-assisted and author-approved (README, figure 1, YAML header, docstring); the
  A1 arm is named the "user-identity variant" throughout (figure 3, READMEs). Code and log identifier stays `ablation_a1`.
- **Docs:** `docs/results.md` adds the post-hoc AP-009 sensitivity analysis, the holdout-robustness caveat and definitions of
  pass^3, errors and cost; `docs/validation/final_corrections/` holds the final correction reports.

## v1.0.0 — 2026-11-13

First publication: agents, mock services, dataset v1.2, frozen scorer v4, raw logs of the 684-run final benchmark, adjudication.
