# Remaining issues

Severity: **High** = must fix before publication (a claim is inaccurate or a primary/secondary result is misframed) ·
**Medium** = should fix before publication · **Low** = fix when convenient · **Info** = no action required.
"Resolved" = fixed in article draft (post-validation) and repository v1.0.1, re-validated on 2026-11-17. No benchmark output was changed.

| ID | Sev. | Affected | Issue | Evidence | Recommended correction | Resolved |
|---|---|---|---|---|---|---|
| V-01 | **High** | Key findings, §9, §10, README | The article declares the frozen scorer primary but leads with adjudicated numbers (headline, pass^3, dev/holdout, authz subset) | Frozen: 74.7% vs 95.6%, Δ +20.9 pp [12.8, 29.0] (2,000 resamples, seed 0; 13.5 with seed 1); pass^3 67.7% vs 93.9%. Adjudicated: 78.5% vs 97.6%, Δ +19.2 pp | Lead with frozen numbers and give adjudicated alongside, or explicitly re-designate adjudicated as primary and say why. Conclusions are unchanged either way (the frozen gap is larger) | Yes — frozen leads in key findings, §9, README, results.md |
| V-02 | **High** | §5.2, fig0c, §6 | "A hash proves what was approved and who approved it" — approver identity is not authenticated | `request_approval` takes `approver_user_id` from the resume payload | Reword (see claims audit); add a §6 row "approver authentication: asserted / needs signed approval or approver session"; label step 6 in fig0c | Yes — §5.2, §6 row, lesson 2, checklist, fig0c, README |
| V-03 | **High** | Key findings, §9, §12, README, results.md | A1 attribution. "Identity alone" removed retrievals is true only together with downstream data scoping; the A1 strict-success delta (+27.2 pp) is not isolated | 0 policy denials in A1; 29 not-found responses; A1 frozen 69.1% vs adjudicated 85.2% (13 runs flipped) | Suggested wording below | Yes — key findings, §8, §9, scorecard, §11, lesson 1, conclusion, README, results.md |
| V-04 | Medium | §9 authz paragraph, fig3 | Authz subset and fig3 show adjudicated values without saying so | Frozen 49.4% → 69.1% → 97.5% | Label "(adjudicated)"; add frozen values in text | Yes — §9 text; fig3 title states adjudicated + frozen values |
| V-05 | Medium | §4, §5.1 | "Policy engine decides every call" — hardened reads bypass `decide` | `graph.py` uses `decide` only in `authorize_action` | Reword: reads scoped by the services and re-checked after fetch; writes decided by the policy engine | Yes — §4, §5.1 |
| V-06 | Medium | §1 | Duplicate anecdote ("never looked up the original") is from the tuning round, not the final run | Final run: 4 baseline runs searched but did not name the original | "…named the hold but did not identify the invoice it duplicated" | Yes — §1 |
| V-07 | Medium | §9 retrieval table | "Disclosed 6" is a post-hoc measure; the frozen scorer reported 0 | Scorer `disclosed` = 0; 6 from status-word check + manual review | Footnote the method and list the six run IDs in the repo | Yes — §9 footnote; run IDs in docs/review_sample_v1.md |
| V-08 | Medium | §9 table, §10 | "0/24 injection successes" is adjudicated; frozen heuristic flagged 3 (B0), 3 (A1), 2 (H) | Recomputed | Label the row and explain the false positives in one clause | Yes — §9 table label + footnote |
| V-13 | Medium | §5.3, tests | "Concurrent duplicates collapse to one effect" is untested in the repo and true only for the same key | Ad hoc: 16 concurrent same-key → 1 effect; 16 distinct keys → 16 effects | Qualify the sentence; add the concurrency test to `tests/` | Yes — §5.3 qualified; test added (12 concurrent same-key → 1 write) |
| V-14 | Medium | `agents/hardened/graph.py` | Approval/idempotency IDs derive only from the action hash: re-requesting an identical action after expiry is immediately expired, and a legitimate later repeat would replay the old result | `approval_id = "APR-"+hash[:12]`, `INSERT OR IGNORE`, expiry read from the first row | Add a per-request nonce (thread/request ID) to the approval ID and idempotency key. Does not affect the published runs (fresh DB, one request per thread). If fixed, version as v1.0.1 and do **not** re-run the benchmark | Yes — v1.0.1 code fix + regression test (fails on v1.0.0); disclosed in §5.2 |
| V-09 | Low | §9 | Bootstrap intervals vary ±1 pp with the seed; holdout lower bound sits at 0.0–1.1 | Seeds 0/1/2 | State "2,000 scenario-clustered resamples" and call the holdout difference borderline | Yes — §8 Statistics paragraph; CIs aligned to published settings |
| V-10 | Low | §8–§10 | Holdout has 29 scored scenarios (AP-009 is holdout) | Scenario file | Say so where holdout results are given | Yes — §8, §9 (29 holdout scenarios) |
| V-11 | Low | §9 performance | Performance uses all 300 executed runs; success uses 297 | H p50 4,050 (300) vs 4,040 ms (297) | One-line population note | Yes — §8 and §9 caption |
| V-12 | Low | §9, fig4 | Cost per successful task = cost of all runs ÷ adjudicated successes | Recomputed | Define in caption | Yes — §9 caption, fig4 title |
| V-15 | Low | §5.4, tests | Circuit breaker and time-based approval expiry have no tests | `grep` of tests | Add tests or say "implemented, not covered by tests" | Yes — breaker and time-based expiry tests added |
| V-16 | Low | §8 / disclosure | Article does not mention the baseline's deliberately over-broad `update_vendor` tool | Design decision D5; tool catalogue | One sentence in §8 | Yes — §8 |
| V-17 | Low | Repo docs | Random-review sample was not preserved | Reconstructed in `review_sample_v1.json` | Add to `docs/` | Yes — docs/review_sample_v1.md |
| V-18 | Low | Makefile / `data/review.py` | `make reproduce-data` writes `docs/dataset_review.md` although the file now lives in `docs/design/` | Observed stray file | Point `review.py` output to `docs/design/` | Yes — review.py writes to docs/design/ |
| V-19 | Low | §5.5 | "prevented the arithmetic slips" is causal wording | 16 retries; 0/15 wrong numbers in H sample | "caught 16 first drafts with unsupported values" | Yes — §5.5 |
| V-20 | Low | §2, §3 references | OWASP #3 ranking and OpenAI guide verified via secondary sources; LangChain page date unverified | `references.md` | Open the three primary pages once before publishing | Partly — OWASP #3 ranking confirmed on the OWASP announcement page; OpenAI PDF and LangChain page date still via secondary sources |
| V-22 | Low | §8 naming | "Identity-only variant" also includes a policy guard (which never fired) | A1 logs | Rename "user-identity variant" | Yes — renamed 'user-identity variant' |
| V-23 | Low | §12 lesson 3 | "payment-affecting write" — crash test used `release_hold` | Test code | "payment-relevant write" | Yes — §12 |
| V-15b | Low | tests | Audit append-only triggers untested | `audit.py` | Add a test | Yes — audit append-only test added |
| V-21 | Info | — | No CSV outputs exist; raw data is JSONL | Repo | None, or add an optional CSV export | n/a |
| V-24 | Info | Logs | Published logs contain synthetic data only: no tokens, keys or unmasked bank numbers | Scan of both run files | None for publication; production logs need redaction | Yes |

## Suggested wording for V-03 (A1 attribution)

> **Key findings:** "Calling the AP services with the user's token instead of a service account stopped every unauthorised
> retrieval in the scenarios where it was tested (18 of 18 runs). The services enforced the user's scope; the agent's policy
> guard never had to refuse a call."
>
> **§9:** "On the 27 authorisation-sensitive scenarios, strict success was 49% → 69% → 97% with the frozen scorer
> (58% → 85% → 100% after adjudication). Retrieval is the clean comparison: 18 unauthorised retrievals for the baseline, none for
> the user-identity variant, and the variant's policy guard never fired — so that result comes from the identity change and the
> services' own scoping. The success-rate difference is not a clean attribution: it also reflects run-to-run variation in other
> scenarios and the adjudication of 13 of the variant's runs."
>
> **Lesson 1:** "Put authorisation where the data lives, and use the user's identity — it only works if the service behind the
> tool enforces that identity."
