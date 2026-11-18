# Final correction report

**Article:** *Your AI Agent Works in a Demo. But Can You Trust It in Production?* · **Date:** 2026-11-17
**Status:** all approved corrections applied on 2026-11-17 (see §6). Raw benchmark outputs unchanged.

## 1. Mandatory corrections — status

| # | Requirement | Finding | Proposed correction | Status |
|---|---|---|---|---|
| 1 | Adjudication terminology | Article says "human review" (key findings) and "human-adjudicated" (§8); §10 says "I reviewed / I overrode"; fig 1 says "After human adjudication"; README says "human adjudication" in three places. The overrides were proposed by an LLM (the AI assistant) and approved by you without per-run re-review | C-01, C-08, C-09, C-10, C-13, C-17; README/YAML/docstring edits | Applied |
| 2 | Identity experiment | Article already uses "User-identity variant (A1)" in prose; tables, README, results README and fig 3 still use other names. Key findings, lesson 1 and conclusion generalise "did most of the security work" beyond the 27 tested scenarios. A1's guard could refuse writes and refused none in all 84 runs | C-02, C-14, C-15, C-17; README edits | Applied |
| 3 | AP-009 sensitivity | Reconciled from raw logs. Original label rewards releasing with a false reason; corrected (post-hoc) criterion = no write + states no receipt. Outcomes: B0 refused 3/3; A1 executed 1/3; H executed 3/3. Overall gap robust (+19.7 to +21.7, frozen); **holdout gap not robust** (crosses zero under the corrected reading) | C-11, C-12; `benchmark_sensitivity_analysis.md` | Applied |
| 4 | Benchmark limitations | pass^3 undefined as a reliability claim; "zero errors" undefined; "$0.73" scope unstated | C-06, C-07; definitions in `benchmark_sensitivity_analysis.md` §3 | Applied |
| 5 | Repository reconciliation | Test counts verified: **139 (v1.0.0), 144 (v1.0.1)** — a version difference. All documented offline commands pass in a clean environment. Figures reconcile to raw data; two labels need changing | C-16, C-17; `repository_consistency_report.md` | Applied |
| 6 | Code and version references | Approval card and code excerpt are v1.0.0; concurrency test is v1.0.1 only; §5.1 overstates the scope re-check. No recommended-only control is described as implemented | C-03, C-04, C-05, C-16 | Applied |

## 2. What was verified, and how

- **Raw data:** unchanged; byte-identical to the uploaded logs (SHA-256 checked in the previous validation).
- **Numbers:** recalculated from raw logs with an independent script; the frozen primary results (74.7% vs 95.6%,
  +20.9 [+12.8, +29.0]) are unchanged.
- **AP-009:** every one of its nine runs read individually from the raw logs; the corrected criterion is applied mechanically.
- **Tests and commands:** executed in this session on clean extracts of both versions.
- **Not verified (by design):** paid commands (`check-model`, `pilot`, `bench-final`); the contents of the live GitHub repository.

## 3. Unresolved items (cannot be verified from available evidence)

| Item | Why unresolved | How the article will treat it |
|---|---|---|
| Cost of the first pilot (direct Anthropic) and of the model-check/probe calls | Not logged | Cost stated as "final-run model API charges"; development costs given where logged ($0.10) |
| Whether the OpenRouter client retried any provider errors silently | Not logged | Mentioned as a limitation |
| Live GitHub contents | No access from this environment | You confirm which version is live |
| OpenAI guide (primary PDF) and LangChain survey page date | Verified only via secondary sources | Wording kept qualitative; low priority |
| Independent human validation of the adjudication | Never performed | Article states this explicitly (C-13) |

## 4. Decisions requiring your approval

1. **Apply corrections C-01 to C-17** to the article, and the matching README, `docs/results.md`, YAML header and docstring
   edits. *(Recommended.)*
2. **Holdout framing:** accept the new statement that the holdout difference is the least robust result (its interval touches zero
   after adjudication and crosses it under the corrected AP-009 reading). *(Recommended — it is what the data shows.)*
3. **Where the AP-009 sensitivity goes:** a short paragraph in §10 (proposed) or a full table in an appendix.
4. **Figure label changes** (fig 1, fig 3) — requires a small edit to `figures.py` and regenerating two charts. Values unchanged.
5. **Scores-file determinism (R-1):** sort one list in the scorer so regenerated `scores.jsonl` is byte-stable. Changes no result,
   but touches the frozen scorer file. *(Optional.)*
6. **Release vehicle:** if v1.0.1 has **not** been pushed, fold these documentation/label changes into v1.0.1; if it **has**, release
   them as v1.0.2. Please confirm which.

## 5. Deliverables in this pass

| File | Contents |
|---|---|
| `final_correction_report.md` | This summary |
| `article_claims_reconciliation.md` | 17 corrections: original, problem, replacement, evidence |
| `benchmark_sensitivity_analysis.md` | AP-009 reconciliation, three scoring treatments, pass^3/errors/cost definitions |
| `ap009_sensitivity.json` | Machine-readable sensitivity results |
| `repository_consistency_report.md` | Versions, test counts, clean-environment command checks, naming/terminology inventory |
| `../final_article.md` | Corrected article (C-01 to C-17 applied) |

## 6. Decisions and application (2026-11-17)

| Decision | Your answer | Applied |
|---|---|---|
| 1. Apply C-01 to C-17 | Yes | ✅ `final_article.md`; README, `docs/results.md`, `results/README.md`, YAML header, docstring |
| 2. Holdout = least robust result | Yes | ✅ §10 (C-12), README table, `docs/results.md` §7 |
| 3. AP-009 sensitivity placement | Short paragraph in §10 | ✅ (C-11); full tables in `docs/results.md` §7 and this folder |
| 4. Figure labels | Change | ✅ fig 1 ("Frozen scorer (primary)" / "Adjudicated (LLM-assisted, author-approved)", one-decimal labels, legend no longer overlaps bars); fig 3 ("User-identity variant (A1)", one-decimal labels) |
| 5. Scorer determinism | Left to me | ✅ Applied: `unsupported_claims` sorted. Verified: 0 value differences across all 684 rows; `scores.jsonl` byte-identical across three `PYTHONHASHSEED` values and on a clean rebuild |
| 6. Release vehicle | v1.0.1 | ✅ all changes folded into v1.0.1 (`CHANGELOG.md` updated) |

**Re-validation on a clean extract of the final v1.0.1 commit:** `make setup` ✅ · `make test` 144 passed ✅ · `make results`
233/297, 290/297, 69/81 ✅ · `make figures` all seven charts reproduce byte-identically ✅ · regenerated `scores.jsonl`
byte-identical to the committed file ✅ · `make reproduce-data` ✅ · `make dry-run` 0 errors ✅.
**Article check:** 35 numeric strings in `final_article.md` matched against the recalculation; 0 mismatches; none of the
superseded phrases ("human review of disputed runs", "human-adjudicated", "Identity-only", "I reviewed every run", "did most of
the security work", "every record it reads") remains.

**Still unresolved:** live GitHub contents (push v1.0.1 to update); cost of the first pilot and of the model-check calls (not
logged); silent provider retries (not logged); OpenAI guide PDF and LangChain page date (secondary sources only).
