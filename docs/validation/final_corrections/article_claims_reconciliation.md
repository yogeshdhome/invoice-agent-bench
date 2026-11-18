# Article claims reconciliation

Source: `article_draft.md` (post-validation draft, 2026-11-17). Each entry gives the original statement, the problem, the proposed
replacement and the evidence. Line numbers refer to that draft. Nothing has been applied yet.

---

### C-01 · Key findings, bullet 1 (L5) — adjudication terminology
**Original:** "…(+21 points, pre-registered scorer; 97.6% vs 78.5% after a human review of disputed runs)…"
**Problem:** The overrides were proposed by an LLM (the AI assistant that built the benchmark) and approved by the author; there
was no human review of individual runs.
**Replacement:** "…(+21 points, pre-registered scorer; 97.6% vs 78.5% after LLM-assisted, author-approved adjudication of
disputed runs)…"
**Evidence:** `docs/adjudication_v1.yaml` (38 overrides authored by the assistant); author's approval message of 2026-11-13.

### C-02 · Key findings, bullet 2 (L6) — identity scope
**Original:** "**User identity did most of the security work; the workflow did most of the correctness work.** Calling the
back-end services with the user's token … stopped every unauthorised retrieval in the scenarios where it was tested (18 of 18
runs) — because the services enforced that user's scope; the agent's policy guard never had to refuse a call."
**Problem:** "did most of the security work" generalises beyond what A1 tested (27 scenarios; the other 4 baseline retrievals
were never run under A1).
**Replacement:** "**In the scenarios where it was tested, user identity did the data-access security work; the workflow did
most of the correctness work.** Calling the back-end services with the user's token instead of a service account stopped every
unauthorised retrieval in those 27 scenarios (18 of 18 runs) — because the services enforced the user's scope. The variant's
policy guard could refuse write calls but never refused one in any of its 84 runs."
**Evidence:** recalculation: A1 retrieved 0/81; 0 policy denials in 84 runs; 4 B0 retrievals (OE-002 ×3, DU-002 ×1) outside
A1's tested set.

### C-03 · §5.1 (L81) — scope re-check
**Original:** "The hardened agent also re-checks the tenant and business unit of every record it reads"
**Problem:** The post-fetch scope check runs only on invoices fetched for a specific-invoice request (`graph.py` line 183).
POs, receipts, vendors and the open-ended search path rely on the services' scoping alone.
**Replacement:** "The hardened agent also re-checks the tenant and business unit of each invoice it fetches for a specific
request"
**Evidence:** `src/invoice_bench/agents/hardened/graph.py:183` — the only `in_scope` call in the graph.

### C-04 · §5.2 card and code (L105, L130) — code version
**Original:** "This is a real card from the benchmark:" … code shows `approval_id = "APR-" + a["hash"][:12]`
**Problem:** Both reflect v1.0.0, the version that produced the results; v1.0.1 changed the approval-ID derivation. A reader
comparing with the repository's current code will see a difference.
**Replacement:** "This is a real card from the final benchmark run, produced by version 1.0.0 of the code:" and, above the code
block, "Excerpt as benchmarked (v1.0.0); v1.0.1 also binds the approval ID to the request — see below."
**Evidence:** run `hardened-AP-001-t0`; `approval_id` = first 12 hex characters of the action hash; v1.0.1 diff in `graph.py`.

### C-05 · §5.3 — concurrency test version
**Original:** "(in the repository's tests, twelve simultaneous requests produced one write and eleven replays)"
**Problem:** That test exists only in v1.0.1.
**Replacement:** "(in a test added in version 1.0.1, twelve simultaneous requests produced one write and eleven replays)"
**Evidence:** `tests/graph/test_v101_controls.py::test_concurrent_same_key_writes_collapse_to_one_effect`.

### C-06 · §8 (L235) — pass^3 meaning
**Original:** "Each scenario ran three times; **pass^3** is the share of scenarios where *all three* runs succeeded."
**Problem:** Readers may read it as a reliability guarantee.
**Replacement:** add: "It is an empirical measure of repeatability on this dataset with three samples per scenario, not a
production reliability rate: a scenario that fails one time in ten still passes all three trials about 73% of the time."
**Evidence:** definition in `bench/stats.py`; 0.9³ = 0.729.

### C-07 · §8 run accounting (L248) — errors, cost, who found AP-009
**Original:** "…whose label I found to be defective *after* the final run, during the review of disagreements described in
Section 10. They are excluded … and **included** in the token and cost totals: 684 runs, 6.14 million tokens, **$0.73** measured
cost, zero errors and zero budget failures."
**Problem:** (a) the defect was found during the LLM-assisted review; (b) "zero errors" is undefined and could be read as "no
failures"; (c) the cost scope is unstated.
**Replacement:** "…whose label was found to be defective *after* the final run, during the LLM-assisted review of disagreements
described in Section 10. They are excluded from every primary success rate, analysed separately in Section 10, and **included**
in the token and cost totals: 684 runs, 6.14 million tokens and **$0.73 in model API charges** (the per-call cost OpenRouter
reported; development runs and local compute are not included). No run ended in a harness or runtime error, and none hit a
budget limit. The 51 failed tool calls in the nine failure scenarios were injected deliberately and are part of what was
scored."
**Evidence:** `benchmark_sensitivity_analysis.md` §3.

### C-08 · §8 Statistics (L252) — adjudication terminology
**Original:** "…the human-adjudicated numbers are a sensitivity analysis (Section 10)."
**Replacement:** "…the adjudicated numbers — overrides proposed by an LLM and approved by the author — are a sensitivity analysis
(Section 10)."
**Evidence:** as C-01.

### C-09 · §9 results table — labels
**Original rows:** "Strict task success — after adjudication", "Difference, adjudicated (95% CI)"
**Replacement:** "Strict task success — adjudicated (sensitivity)", "Difference, adjudicated (sensitivity, 95% CI)"
**Evidence:** methodology §8: frozen scorer is primary.

### C-10 · §9 footnote ¹ (L289) — who identified disclosures
**Original:** "…I identified them after the run by checking every cross-scope answer for the invoice's status and reading each
one."
**Replacement:** "…They were identified after the run by an automated check of every cross-scope answer for the invoice's status,
and each was then confirmed by the AI assistant reading the answer."
**Evidence:** validation `recalc.py` (status-word check); `docs/review_sample_v1.md`.

### C-11 · §10 AP-009 paragraph (L337) — sensitivity analysis
**Original:** ends "…I excluded AP-009 from the success rates because its label rewarded executing the false reason — but the
finding stands, and it points at the next control to build."
**Problem:** No quantified impact of the exclusion; "I excluded" omits that the exclusion was post-hoc.
**Replacement:** "…AP-009 was excluded from the primary success rates, after the run, because its label rewarded executing the
false reason. Counting it either way does not change the overall conclusion: the hardened-vs-baseline gap is +20.9 points with
AP-009 excluded, +21.7 under its original label and +19.7 if it is re-scored post hoc so that refusing the false reason counts as
correct. The holdout comparison is different: AP-009 is a holdout scenario, and under the corrected reading the holdout interval
crosses zero (+14.4 [−2.2, +32.2])."
**Evidence:** `benchmark_sensitivity_analysis.md` §1–2.

### C-12 · §10 overfitting paragraph — holdout fragility
**Original:** "…The baseline's drop was smaller: 78.6% vs 78.2% adjudicated, 75.7% vs 72.4% frozen."
**Replacement:** append: "The holdout difference between the two agents is the least robust number in this article: its
confidence interval touches zero after adjudication and crosses it if AP-009 is counted under the corrected reading."
**Evidence:** `benchmark_sensitivity_analysis.md` §2.

### C-13 · §10 adjudication paragraphs (L345, L347) — process description
**Original (L345):** "After the final run I reviewed every run it found suspicious … I overrode 38 judgements … The criteria I
applied…"
**Original (L347):** "…It was performed by **one reviewer**: the AI assistant that helped build the system, with the overrides
then approved by me. … a random check of fifteen scored passes per arm (listed in the repository) found…"
**Problem:** First-person "I reviewed / I overrode" misattributes the work; the random check was also performed by the LLM.
**Replacement (L345):** "After the final run, the AI assistant I used to build the benchmark reviewed every run the scorer found
suspicious: 63 runs, across all 684, where its outcome class differed from the expected one, plus 10 other runs whose automated
verdicts looked wrong on inspection (8 injection flags, 2 numeric mismatches). It proposed 38 overrides — 19 for the baseline, 13
for the user-identity variant, 6 for the hardened agent — which I approved; they changed the strict result of 11, 13 and 6 runs
respectively. The criteria applied, consistently across arms: …"
**Replacement (L347):** "Three honest caveats about that process. It was **not blinded** — run identifiers reveal which agent
produced each answer. It was performed by **one reviewer, an LLM**: the AI assistant that helped build the system. I approved its
overrides without re-reviewing each run, and no independent human reviewer checked them. Two things limit the risk: the
overrides helped the baseline and the user-identity variant more than the hardened agent, and a random spot check of fifteen
scored passes per arm — also performed by the assistant, and listed in the repository — found two baseline answers with wrong
numbers that the scorer had accepted, and none for the hardened agent. On balance the automated scorer flatters the baseline
slightly. A blinded, independent human review is the right next step."
**Evidence:** conversation record; `docs/adjudication_v1.yaml`; `docs/review_sample_v1.md`.

### C-14 · A1 naming (L230, L245, L281 and elsewhere)
**Original:** "User-identity variant (A1)", "User-identity (A1)" (tables)
**Replacement:** "User-identity variant (A1)" everywhere, including table headers and figure labels.
**Evidence:** naming inventory in `repository_consistency_report.md`.

### C-15 · Lesson 1 and Conclusion — identity scope
**Original (lesson 1):** "…It was the cheapest control in this study and did most of the security work — because the services
enforced the user's scope."
**Replacement:** "…It was the cheapest control in this study, and in the 27 scenarios where it was tested it removed every
unauthorised retrieval — because the services enforced the user's scope."
**Original (conclusion):** "First, **the cheapest control did most of the security work**: …"
**Replacement:** "First, **the cheapest control did the data-access security work**: …" (rest unchanged)
**Evidence:** as C-02.

### C-16 · §13 Reproduce it — test count and versions
**Original:** "make setup && make test        # 144 offline tests, no API key" and "Version 1.0.1 changes code and documentation
only…"
**Problem:** v1.0.0 (the benchmarked version, and the one on GitHub at the time of the last confirmation) has 139 tests; v1.0.1
has 144.
**Replacement:** "make setup && make test        # 144 offline tests in v1.0.1 (139 in v1.0.0), no API key" and "The benchmark
was run on version 1.0.0 (tag `v1.0.0`). Version 1.0.1 adds the approval fix described in Section 5.2, five tests and corrected
documentation; it changes no published result."
**Evidence:** clean-archive runs: v1.0.0 commit `60a3032` → 139 passed; v1.0.1 → 144 passed.

### C-17 · Figures 1 and 3 — labels
**Original:** fig 1 x-axis "After human adjudication"; fig 3 tick label "A1: B0 + user-scoped identity".
**Replacement:** "Adjudicated (LLM-assisted, author-approved)"; "User-identity variant (A1)". Values unchanged.
**Evidence:** `src/invoice_bench/bench/figures.py` lines 16 and 35.

---

## Claims re-checked and left unchanged

| Claim | Status |
|---|---|
| All headline, pass^k, holdout, authz, latency, token, cost and call figures | ✅ match raw-log recalculation |
| "Writes executed without valid approval: 0 / 0" | ✅ |
| "No arm produced a duplicate side effect" | ✅ |
| Production controls described as implemented (scoping, write policy, hash binding, expiry, segregation-of-duties check, idempotency, retries, breaker, grounding, append-only audit) | ✅ present in code; breaker and append-only covered by tests only from v1.0.1 |
| Controls described as recommended (approver authentication, reason validation, re-authorisation before execution, durable checkpointer, gateway, audience validation, redaction, load testing) | ✅ described as not implemented |
| External references | ✅ as in `references.md`; OpenAI guide and LangChain page date still via secondary sources (**unresolved**, low) |
