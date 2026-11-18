# Publication validation report

**Article:** *Your AI Agent Works in a Demo. But Can You Trust It in Production?* · **Repository:** invoice-agent-bench v1.0.0
**Date:** 2026-11-17 · **Scope:** benchmark data, code, tests, figures, README, article draft, references.
No paid API calls were made; no benchmark output was modified; nothing was published.

## Verdict (initial review, v1.0.0): **READY AFTER MINOR CORRECTIONS** — see §8 for the re-validation verdict

Every published number reproduces from the raw logs, and every documented command runs from a clean copy. The corrections
needed are wording and labelling, not new experiments: three high-severity claim issues (V-01 to V-03) and six medium ones
(V-04 to V-08, V-13). One medium code defect (V-14) does not affect the published results.

**Blockers before publishing:** V-01 (primary vs adjudicated framing), V-02 (approver identity claim), V-03 (A1 attribution).
Recommended in the same pass: V-04 to V-08 and V-13.

## 1. What was validated

| Check | Result |
|---|---|
| Raw logs in the bundle identical to the logs uploaded from the benchmark machine | ✅ SHA-256 match for both files |
| `make setup` | ✅ |
| `make test` | ✅ 139 passed |
| `make results` | ✅ reproduces 233/297, 290/297, 69/81; `summary.json` identical to the published copy |
| `make figures` | ✅ all regenerated charts identical to the published ones; article figures pixel-identical to the repository copies |
| `make reproduce-data` | ✅ dataset manifest and hashes identical (world `48b5e59f…`, dev `25ad9d03…`); writes one stray file (V-18) |
| `make dry-run` | ✅ 300 runs, 0 errors |
| Independent recalculation of every published metric | ✅ all values reproduce; see `benchmark_reconciliation.md` |
| Secrets in published logs | ✅ none found |

## 2. Benchmark findings in brief

- Accounting reconciles exactly: 684 executed, 675 scored, 9 AP-009 runs excluded from success rates and included in cost.
  AP-009 is a **holdout** scenario, so the holdout has 29 scored scenarios.
- Every frozen and adjudicated rate, pass^k value, confidence interval, latency percentile, token count and cost figure in the
  article reproduces from raw data. Bootstrap bounds move by about ±1 pp with the random seed.
- **Framing problem (V-01):** the article names the frozen scorer as primary but its headline, pass^3, dev/holdout and
  authorisation numbers are adjudicated. The frozen results tell the same story with a *larger* gap (+20.9 pp vs +19.2 pp), so
  fixing this costs nothing in substance.

## 3. The A1 question

The task asked whether the article can say identity alone caused the security improvement. The evidence:

- A1 = baseline + user's token + a policy guard on writes. **The guard denied zero calls in 84 runs.**
- All 18 cross-scope lookups in A1 returned not-found because the AP services scoped reads to the user's token.
- Therefore the **retrieval** result (18 → 0) is attributable to user-scoped identity *as enforced by the downstream service* —
  not to the policy engine, and not to identity in isolation from the service behaviour.
- The **strict-success** difference (B0 → A1) is *not* a clean attribution: A1 is the arm most affected by adjudication
  (69.1% frozen → 85.2% adjudicated), and the other authorisation scenarios vary with the model run-to-run.

Recommended wording is in `remaining_issues.md` (V-03). No additional ablation is needed if that wording is adopted.

## 4. Implementation and security in brief

Implemented and tested: tenant/business-unit scoping, cross-tenant blocking, action-hash binding, segregation-of-duties check,
idempotent writes (sequential), crash-and-resume without duplicates, retries, grounding, planner isolation from vendor text.

Gaps that the article must describe accurately:
- **Approver identity is asserted, not authenticated (V-02).** The segregation-of-duties check runs against whatever approver
  ID the approval channel supplies.
- **Hardened reads do not go through the policy engine (V-05).** They rely on service scoping plus a post-fetch check.
- **Approval re-use defect (V-14)** in the hardened code; not triggered in the benchmark.
- Concurrent same-key de-duplication verified only ad hoc (V-13); circuit breaker, time-based expiry and audit append-only
  triggers have no tests (V-15).

Full table: `security_review.md`.

## 5. Article in brief

45 claims audited (`article_claims_audit.md`): 22 supported as written, 20 need wording or labelling, and three are
inaccurate as written (§1 duplicate anecdote, §5.1 "decides every call", §5.2 "who approved it"). All figures exist, are
readable and match the data; fig 3 and fig 4 need captions stating that they use adjudicated values. Three external references
were verified only through secondary sources and should be opened once before publishing (V-20).

## 6. Files

| File | Contents |
|---|---|
| `benchmark_reconciliation.md` | Every published metric, recomputed, with status |
| `security_review.md` | 17 threats: control, status, evidence, gap |
| `article_claims_audit.md` | Claim-by-claim, figure and reference audit |
| `remaining_issues.md` | 25 issues with severity, evidence, correction, resolution status, and suggested A1 wording |
| `recalc.py`, `recalculated_metrics.json` | Independent recalculation script and its output |
| `review_sample_v1.json` | Reconstructed random review sample (30 run IDs) |

## 7. Proposed next step

With your approval: (1) apply the text corrections for V-01 to V-13 to the article, README and `docs/results.md`;
(2) optionally fix V-14, V-15, V-18 in code and tests as **v1.0.1** without re-running the benchmark; (3) re-run this
validation to confirm. Publication remains your decision.

## 8. Re-validation after corrections (2026-11-17, repository v1.0.1)

All corrections were applied to the article draft, README, `docs/results.md`, figures and code. No benchmark output was
modified; the raw logs are byte-identical to those validated above.

| Check | Result |
|---|---|
| `make setup` / `make test` | ✅ 144 passed (5 new tests: concurrent same-key writes, time-based expiry, fresh approval on repeated request, circuit breaker, append-only audit) |
| Regression test for V-14 | ✅ fails on v1.0.0 code, passes on v1.0.1 |
| `make results` | ✅ 233/297, 290/297, 69/81 — unchanged |
| `make figures` | ✅ all charts regenerate identically to the committed v1.0.1 figures; article figures replaced with these |
| `make reproduce-data` | ✅ identical hashes; stray file no longer created |
| `make dry-run` | ✅ 0 errors |
| Independent recalculation | ✅ identical to the v1.0.0 validation output |
| Article numbers vs recalculation | ✅ 18 checked groups, all present and correct |

**Issue status:** 23 of 25 resolved; V-20 partly resolved (the OWASP ranking is now confirmed on OWASP's own page; the OpenAI
guide and the LangChain survey page date are still verified only through secondary sources); V-21 needs no action.

## Final verdict: **READY TO PUBLISH** — once repository v1.0.1 is on GitHub

The article now cites v1.0.1 artefacts (144 tests, `CHANGELOG.md`, `docs/review_sample_v1.md`, `docs/validation/`). The
GitHub repository currently holds v1.0.0, so pushing v1.0.1 is the only remaining blocker. Optional before publishing: open
the OpenAI guide PDF and the LangChain survey page once (V-20).
