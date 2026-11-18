# Article claims audit

Draft audited: `article_draft.md` (current version, 2026-11-13). ✅ supported · ⚠️ supported but needs wording/label · ❌ unsupported or inaccurate.

## Quantitative and factual claims

| § | Claim | Evidence | Verdict | Correction |
|---|---|---|---|---|
| Key findings | 97.6% vs 78.5% (+19 points); 97.0% vs 72.7% pass^3 | Adjudicated values reproduce | ⚠️ | The article calls the frozen scorer primary but leads with adjudicated numbers. Lead with frozen (95.6% vs 74.7%, +20.9 pp; pass^3 93.9% vs 67.7%) or show both |
| Key findings | "Identity … stopped every unauthorised retrieval … (18 of 18 runs)" | A1 retrieved 0/81; policy guard never fired | ⚠️ | Say "user-scoped identity, enforced by the downstream services' data scoping" |
| Key findings | "faster at the median; about 5× fewer tokens" | p50 4.05 vs 4.64 s (CIs disjoint); 13,698 / 2,646 = 5.2× | ✅ | — |
| §1 | Third of cross-scope runs disclosed status | 6/18 | ✅ | Note the measurement (post-hoc review) in §9 |
| §1 | PO timed out twice; retried once; gave up | TF-001 B0, all trials | ✅ | — |
| §1 | Controller-approved release refused | AP-002 B0, 2 of 3 trials | ✅ | — |
| §1 | Duplicate: "never looked up the original" | Final run: searched but failed to name the original (4 runs) | ❌ | "…named the hold but did not identify the invoice it duplicated" |
| §2 | Endpoint does not accept temperature | Zero-token endpoint check output (supported parameters list) | ✅ | — |
| §2 | OWASP Agentic Top 10 (Dec 2025); LLM Top 10 2026 moved Excessive Agency to #3 | Release confirmed (OWASP page + reports); the #3 placement verified only via a secondary report | ⚠️ | Confirm on the OWASP 2026 list page before publishing |
| §2 | LangGraph re-runs a resumed node from the top | LangGraph interrupts docs | ✅ | — |
| §2 | LangChain survey: quality top barrier; observability near-universal; offline evals lag | Survey page (headline figures); offline-eval figure via secondary | ⚠️ | Keep qualitative wording (as written) |
| §3 | OpenAI guide: start with one agent | Verbatim excerpts of the guide (secondary host) | ⚠️ | Open the primary PDF once to confirm |
| §3 | MAST 1,600+ traces, 14 failure modes; Anthropic ~15× tokens | Primary sources | ✅ | — |
| §4 | "every tool call is authorised in code regardless of what the model asks for" | Hardened model chooses no tool calls; reads scoped by service + post-check; writes via policy | ⚠️ | "The model never chooses a tool call: reads are scoped to the user by the services, and every write goes through the policy engine" |
| §4 | Delimiters are not the security boundary | Design + tests | ✅ | — |
| §5.1 | "a deterministic policy engine decides every call" | `decide` used only for writes in H | ❌ | As above |
| §5.1 | "The principal comes from a verified token" | Services verify the token; the graph receives the principal from the harness | ⚠️ | "…comes from the authenticated session (in the benchmark, issued by the harness), never from the prompt or the model" |
| §5.2 | Real approval card | Run record AP-001 t0 | ✅ | — |
| §5.2 | "A hash proves what was approved **and who approved it**" | Approver ID unauthenticated (S6) | ❌ | "…proves what was approved; the approver's identity is checked for role and segregation of duties, but in the benchmark it is asserted by the approval channel, not authenticated" |
| §5.2 | Expiry and segregation of duties checked | Code + tests (expiry via 'expired' path only) | ⚠️ | Mention the approval re-use defect only if the code is not fixed |
| §5.3 | Crash-after-write test, one action-log row | `test_crash_after_write…` | ✅ | — |
| §5.3 | "no arm produced a duplicate side effect" in 684 runs | Scorer metric = 0 | ✅ | — |
| §5.3 | "concurrent duplicates also collapse to one effect" | Ad hoc only; same key only | ⚠️ | "…concurrent requests carrying the same key also collapse to one effect (verified ad hoc; requests with different keys do not)" and add the test |
| §5.4 | Retry/backoff/breaker parameters | `resilient.py`, `settings.yaml` | ✅ | Add "the breaker is not covered by tests" |
| §5.5 | Grounding "prevented the arithmetic slips the baseline made" | 16 retries; 0/15 wrong numbers in H review sample | ⚠️ | "…caught 16 first drafts with unsupported values" |
| §5.6 | Run anatomy table | Run record | ✅ | — |
| §6 | Implemented-vs-needed table | Code inspection | ⚠️ | Add a row: approver authentication — "asserted, not authenticated" / "signed approvals or approver session" |
| §7 | reasoning `enabled:false` ≈ 200 tokens; `effort:none` 0 | Probe output (197, 223, 0) | ✅ | — |
| §8 | 100 scenarios, 30 holdout | AP-009 is a holdout scenario | ⚠️ | "29 holdout scenarios after the exclusion" wherever holdout results appear |
| §8 | A1 described as "identity-only … and the policy engine can refuse a call" | Guard never fired | ⚠️ | Rename "user-identity variant"; add "in 84 runs the guard never had to refuse a call" |
| §8 | Latency "roughly 100–300 ms per call" | Profile medians 100–300 ms (log-normal) | ⚠️ | "median 100–300 ms" |
| §8 | Run accounting table | Recomputed | ✅ | Add "AP-009 is a holdout scenario" |
| §9 | Main results table | Recomputed | ⚠️ | Add frozen pass^3 and frozen holdout; label the injection row "after adjudication (frozen heuristic flagged 3/2 runs, all false positives)" |
| §9 | Retrieval table | Recomputed | ⚠️ | Footnote: "disclosed" measured by post-hoc review; the frozen scorer's forbidden-fact check found none |
| §9 | Authz: 58% → 85% → 100%, deltas | Adjudicated values reproduce; frozen 49% → 69% → 97% | ⚠️ | Show both; drop "Identity removed … (A1 − B0: +27.2 pp)" pairing — the delta is not isolated |
| §9 | Performance table | Recomputed | ⚠️ | State population: all executed runs (300 per arm) |
| §9 | Hypothesis scorecard | Consistent with data | ✅ | — |
| §10 | AP-009 behaviour (5/6 refused vs 3/3) | Recomputed | ✅ | — |
| §10 | 7 hardened failures (4 template, 3 MM-005; 6 holdout) | Recomputed | ✅ | — |
| §10 | Dev 99.5% vs holdout 93.1%; B0 78.6% vs 78.2% | Recomputed (adjudicated) | ⚠️ | Label adjudicated; frozen 97.6% vs 90.8% and 75.7% vs 72.4% |
| §10 | Adjudication counts 63 + 10; 38 overrides; 11/13/6 | Recomputed | ✅ | "63 across all 684 runs" |
| §10 | Random review: 2/15 B0 wrong, 0/15 H | Reconstructed sample | ✅ | Publish `review_sample_v1.json` |
| §12 | Lesson 3 "payment-affecting write" | Crash test used `release_hold` | ⚠️ | "payment-relevant write" |
| §13 | 139 offline tests; commands | Ran all documented commands successfully | ✅ | — |
| Disclosure | Model ID and routing | Manifests | ✅ | Add "the baseline was given an over-broad vendor-update tool (to model real API bundling)" |

## Figures

| Figure | Values | Readability | Verdict |
|---|---|---|---|
| fig0a, fig0b (architecture, workflow) | Match code paths | Readable | ✅ |
| fig0c (approval sequence) | Step 7 "check hash, expiry, approver ≠ requester" is implemented; step 8 dashed "recommended" | Readable | ⚠️ add "approver identity asserted, not authenticated" to step 6 label |
| fig1 (strict success) | Frozen and adjudicated, Wilson CIs | Readable | ✅ |
| fig2 (pass^k) | Adjudicated; title says so | Readable | ✅ |
| fig3 (authz ablation) | Adjudicated; **title does not say so** | Readable | ⚠️ add "(adjudicated)" or a frozen panel |
| fig4 (efficiency) | Tokens all runs; cost per adjudicated success | Readable | ⚠️ add caption with definitions |

## External references

| Reference | Date | Supports | Status |
|---|---|---|---|
| Yao et al., τ-bench, arXiv 2406.12045 | 2024-06-17 | pass^k definition | ✅ primary |
| Anthropic, Building effective agents | 2024-12-19 | workflows vs agents | ✅ primary |
| OpenAI, A practical guide to building agents | 2025 | start with a single agent | ⚠️ verified via verbatim excerpts; open the PDF |
| Cemri et al., MAST, arXiv 2503.13657 | 2025-03 (v3 2025-10) | 14 failure modes, 1,600+ traces | ✅ primary |
| Anthropic, multi-agent research system | 2025-06-13 | ~15× tokens | ✅ primary |
| OWASP Agentic Top 10 | 2025-12-10 | identity/privilege abuse risk | ✅ |
| OWASP LLM Top 10 2026 | 2026-08-03 | Excessive Agency #3 | ⚠️ ranking via secondary report |
| LangGraph interrupts docs | living | node re-runs on resume | ✅ primary |
| LangChain, State of Agent Engineering | survey late 2025; page date unverified | quality barrier, observability vs evals | ⚠️ |
| Microsoft AI Red Team taxonomy update | 2026-06-04 | HitL bypass most consistently exploited | ✅ primary |
| NIST CAISI agent hijacking blog | 2025-01-17 | repeated attempts more realistic | ✅ primary |
