# Repository consistency report

Checked on clean `git archive` extracts in a fresh environment (no cached virtualenv, no prior outputs). No paid API calls.

## 1. Versions

| Version | Commit (local) | Status | Produced the published runs? |
|---|---|---|---|
| v1.0.0 | `60a3032` | On GitHub as of your last confirmation | **Yes** |
| v1.0.1 | `fd01b9b` + `194108a` (validation docs) | Prepared, **not confirmed pushed** | No — code/docs fixes only; scores identically |

**Unresolved:** I cannot access GitHub from this environment, so the live repository's contents are unverified.

## 2. Offline test count (`make test`, i.e. `pytest -m "not llm"`)

| Version | Result |
|---|---|
| v1.0.0 | **139 passed** |
| v1.0.1 | **144 passed** (+5 in `tests/graph/test_v101_controls.py`) |

The "139 vs 144" discrepancy is a version difference, not an error. The article and README must name the version with each count
(article correction C-16).

## 3. Documented commands (clean environment, v1.0.1)

| Command | Result |
|---|---|
| `make setup` | ✅ |
| `make test` | ✅ 144 passed |
| `make results` | ✅ 233/297, 290/297, 69/81 (adjudicated); `summary.json` identical to the published copy |
| `make figures` | ✅ charts regenerate; pixel-identical to the committed figures |
| `make reproduce-data` | ✅ identical dataset hashes; no stray files |
| `make dry-run` | ✅ 300 runs, 0 errors |
| `make diagrams` | ✅ (needs Graphviz on PATH; verified earlier in this environment) |
| `make check-model`, `make pilot`, `make bench-final` | **Not run** — require a paid API key; out of scope |

## 4. Figures vs data

All seven figures regenerate from the raw logs and match the published values (see validation `benchmark_reconciliation.md`).
Label corrections needed (values unchanged):

| Figure | Current label | Required |
|---|---|---|
| fig1 | x-axis "After human adjudication" | "Adjudicated (LLM-assisted, author-approved)" |
| fig3 | "A1: B0 + user-scoped identity" | "User-identity variant (A1)" |

## 5. Terminology and naming inventory (files to change)

| File | Current | Required |
|---|---|---|
| `README.md` L12 | "**Identity-only (A1)** … a policy engine can refuse a call" | "**User-identity variant (A1)** … a policy guard can refuse write calls (it never refused one in the published runs)" |
| `README.md` L21 | "human adjudication is a sensitivity analysis" | "LLM-assisted, author-approved adjudication is a sensitivity analysis" |
| `README.md` L94 | "Every human override of the frozen scorer" | "Every adjudication override of the frozen scorer (proposed by an LLM, approved by the author)" |
| `README.md` L118 | "human adjudication was not blinded and was performed by one reviewer (the AI assistant…)" | "adjudication was LLM-assisted (one AI reviewer, not blinded) and approved by the author without independent human review" |
| `docs/adjudication_v1.yaml` header | `adjudicator: Claude (author review pending)` | `adjudicator: LLM assistant (Claude); approved by the author 2026-11-13; not independently re-reviewed` |
| `src/invoice_bench/bench/adjudicate.py` docstring | "Apply human adjudication…" | "Apply LLM-assisted, author-approved adjudication…" |
| `src/invoice_bench/bench/figures.py` | labels above | as §4 |
| `docs/results.md` | A1 described as "A1"; no AP-009 sensitivity; no pass^3/errors/cost definitions | add "User-identity variant (A1)", the AP-009 sensitivity table and the three definitions |
| `results/README.md` | "A1" | "User-identity variant (A1)" |
| Code identifiers (`ablation_a1`) | — | **Keep** (renaming would change raw-log keys); document the mapping in README |

## 6. Other findings

| ID | Finding | Severity | Proposed action |
|---|---|---|---|
| R-1 | `results/final/report/scores.jsonl` is not byte-stable: the `unsupported_claims` list order varies between regenerations (Python set order). 7 rows differ between v1.0.0 and v1.0.1 copies; no value or metric differs | Low | Sort the list in the scorer (one line; changes no result) — **your decision** |
| R-2 | `make check-model`/`pilot`/`bench-final` cannot be verified without paid calls | Info | State in README that these were verified only on the author's machine |
| R-3 | First pilot (direct Anthropic) cost was not logged | Info | State as unresolved in article/README cost note |
| R-4 | Article figures folder vs repository figures | ✅ pixel-identical today; must be regenerated together after the label fix | — |
