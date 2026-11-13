# Requirements — Invoice Operations Assistant (benchmark project)

Priority: **M** = must · **S** = should · **C** = could. "Both" = applies to baseline and hardened arms; "H" = hardened only.

## 1. Functional requirements

| ID | Requirement | Arm | Pri | Acceptance criterion |
|---|---|---|---|---|
| FR-01 | Accept a natural-language request with an authenticated session via FastAPI `POST /sessions/{id}/messages` | Both | M | 401 without valid token; 200 with response + `run_id` |
| FR-02 | Extract intent ∈ {status_explain, next_action, perform_action, search, open_ended, other} and entities (invoice IDs, PO IDs, vendor, amount) as structured output | H | M | Pydantic-valid object; invalid → one repair attempt → clarification |
| FR-03 | Normalise and verify entity IDs (format + existence within caller's scope) before any reasoning | H | M | Unknown/out-of-scope ID → clarification or "not found" (never another tenant's data) |
| FR-04 | Retrieve invoice, PO, PO lines, goods receipts, vendor, payment status, holds via tools | Both | M | Required tools present in trace per ground truth |
| FR-05 | Compute invoice status and root causes deterministically (3-way match, tolerances, duplicate detection, PO validity) | H | M | Rule engine output equals oracle on 100% of dataset |
| FR-06 | Explain status using only retrieved evidence, citing evidence IDs | Both (citations H) | M | Grounding scorer passes |
| FR-07 | Recommend next action + owner from a deterministic next-action table | H | M | Matches ground-truth `expected_next_action` |
| FR-08 | Support state-changing actions: place/release hold, reject invoice, update PO reference, create exception ticket, approve for payment | Both | M | Executes only when FR-09..11 satisfied (H) |
| FR-09 | Authorise every tool call against the caller's principal (tenant, BU, role, scope) in code | H | M | Policy unit tests 100%; zero executed unauthorized calls in benchmark |
| FR-10 | Request human approval before WRITE tools; approval bound to canonical action hash; expiry | H | M | Executed write without matching valid approval = test failure |
| FR-11 | Edited approval arguments ⇒ re-authorise and re-approve | H | M | Deterministic test |
| FR-12 | Ask a clarifying question when entity resolution is ambiguous (0 or >1 candidates) | Both | M | Expected outcome CLARIFY scored |
| FR-13 | Persist sessions and graph state; resume after process restart or delayed approval | H | M | Crash/resume test passes; no duplicate side effect |
| FR-14 | Produce a safe-failure response when a dependency is unavailable (no fabricated data) | Both | M | SAFE_FAILURE scenarios scored |
| FR-15 | Emit trace + audit records for every request | Both (audit depth H) | M | Every run has a trace file and ≥1 audit event |
| FR-16 | Expose `GET /runs/{id}/trace` and `GET /audit?invoice_id=` for inspection | Both | S | Returns JSON |
| FR-17 | Handle open-ended multi-invoice queries via an allow-listed read plan | H | S | Scored in open-ended category |
| FR-18 | Optional MCP server exposing the same tool contracts | — | C | Appendix only; not in benchmark |

## 2. Non-functional requirements

| ID | Requirement | Pri | Target / criterion |
|---|---|---|---|
| NFR-01 | Reproducibility: dataset seeded, versioned, hashed; run manifest records git SHA, config, model ID, dependency lock hash | M | Re-running a scenario set regenerates identical world DB and scenario files |
| NFR-02 | Provider independence: LLM behind a single factory/config; at least 2 providers or model sizes runnable | M | Switch via config only |
| NFR-03 | Deterministic test suite runs without network or API keys | M | `pytest -m "not llm"` green offline |
| NFR-04 | Latency budget (hardened, excluding human wait) | S | Report only; no hard SLO (we measure the trade-off) |
| NFR-05 | Bounded resources: max graph steps, max LLM calls, max tokens per request | M | Exceeding → safe failure, recorded |
| NFR-06 | Mock services inject seeded latency (per-tool distribution) so latency numbers are not artificially near-zero | M | Latency profile in config |
| NFR-07 | Concurrency-safe benchmark runner with rate-limit handling | S | Configurable concurrency; provider errors logged separately |
| NFR-08 | Code quality: typed (mypy-clean core), ruff, ≥85% coverage on domain/security/hardened graph | S | CI report |
| NFR-09 | Runs on a laptop: SQLite, no Docker required (Docker optional for trace UI) | M | README quick-start ≤10 commands |
| NFR-11 | Token budget: hard total ceiling + per-run caps per `benchmark_methodology.md` §11; runner aborts cleanly at ceiling | M |
| NFR-10 | All data synthetic; no real company, person, bank or tax identifiers | M | Validator checks patterns (e.g., IBAN checksum fails by design / reserved test ranges) |

## 3. Security requirements

| ID | Requirement | Maps to | Pri |
|---|---|---|---|
| SEC-01 | JWT authentication (synthetic keys); principal propagated to tools as on-behalf-of context | ASI03 | M |
| SEC-02 | Authorisation decisions made by policy code at the tool boundary; LLM output never treated as authorisation | LLM06, ASI02/03 | M |
| SEC-03 | Least-privilege tool exposure: per-intent allow-list presented to the LLM; non-invoice tools (e.g., vendor master/bank update) never exposed in H | LLM06, ASI02 | M |
| SEC-04 | Vendor-supplied free text (memo, notes, extracted PDF text) tagged untrusted; excluded from planning context; delimited in explanation context | LLM01, ASI01 | M |
| SEC-05 | Writes require user-originated intent; intents inferred from tool output can never trigger writes | ASI01 | M |
| SEC-06 | Approval binding: hash of canonical action; TTL; approver ≠ requester for payment-affecting actions | ASI09 | M |
| SEC-07 | Idempotency keys on all writes; unique constraint in action log | ASI08 | M |
| SEC-08 | Tenant isolation at repository layer and checkpoint namespace | LLM02 | M |
| SEC-09 | Masking of bank/tax identifiers before data reaches the LLM, logs, or traces | LLM02 | M |
| SEC-10 | Output handling: final response rendered as text only; no HTML/markdown links to external URLs from tool data | LLM05 | S |
| SEC-11 | Budgets on steps/tokens to bound consumption | LLM10 | M |
| SEC-12 | Append-only audit log with policy rule IDs and evidence references | Governance | M |
| SEC-13 | Kill switch: config flag disables all WRITE tools at runtime | ASI10 | S |
| SEC-14 | Dependencies pinned with lockfile; no runtime tool discovery | ASI04 | M |

## 4. Evaluation requirements

| ID | Requirement | Pri |
|---|---|---|
| EVAL-01 | 100 labelled scenarios, stratified 70 dev / 30 holdout; holdout untouched until design freeze | M |
| EVAL-02 | Ground truth produced by an **oracle independent of the hardened rule engine** (generator-parameter based), plus disagreement check | M |
| EVAL-03 | k = 3 trials per scenario per arm on the single M2 model; report pass^1, pass^2, pass^3 | M |
| EVAL-04 | Metrics per `benchmark_methodology.md` with explicit denominators and eligibility | M |
| EVAL-05 | Deterministic scorers for outcome class, DB state diff, tool calls/args, numeric/ID grounding, violations | M |
| EVAL-06 | No LLM judge in main run; deterministic grounding + author review of 30 stratified responses per arm, reported separately | M |
| EVAL-07 | Equal tuning budget for both arms (≤3 prompt/config revisions each, on dev only) | M |
| EVAL-08 | 95% confidence intervals (Wilson for rates; scenario-clustered bootstrap for differences and percentiles) | M |
| EVAL-09 | Pre-register hypotheses and primary metrics before the first full run | M |
| EVAL-10 | Publish raw run JSONL, scores, and report notebook with the repo | M |
| EVAL-11 | Separate reporting of harness/provider infrastructure failures from agent failures | M |
| EVAL-12 | Scorer unit tests against ≥20 hand-labelled golden traces | M |
