# Research Notes — Article 01: Production-Ready Enterprise AI Agents

Research date: 2026-11-11. Running example: Enterprise Invoice Operations Assistant (synthetic).

**Labels:** **[F]** fact from a cited source (see `references.md`, R-ids) · **[I]** inference/engineering judgement · **[S]** speculation/hypothesis to be tested by the benchmark. Confidence: **H / M / L**.

---

## 0. Executive findings (what should shape the article)

1. **Single-trial demos hide the real problem: consistency.** τ-bench introduced `pass^k` (probability that *all* k trials of the same task succeed); strong function-calling agents degraded sharply from pass^1 to pass^8 in the retail domain. [F, H — R08] → Our benchmark must run repeated trials and report pass^k, not just average success.
2. **The industry gap is evaluation, not tracing.** In LangChain's survey, quality was the top production blocker (~32%), observability is near-universal, but offline evals lag well behind. [F, survey, M — R14] Treat as survey of LangChain's audience, not a universal fact.
3. **Most "agent" reliability comes from moving decisions out of the model.** Anthropic distinguishes workflows (predefined code paths) from agents (model directs its own process) and recommends the simplest pattern that works. [F, H — R11] The hardened design should be a *workflow spine with LLM decisions at the edges*. [I, H]
4. **Prompt injection is best mitigated architecturally, not by prompting.** Six design patterns (action-selector, plan-then-execute, map-reduce, dual-LLM, code-then-execute, context-minimization) constrain what untrusted data can influence. [F, H — R06] Caveat: these patterns fix *which* tool runs, not necessarily the *arguments*; argument provenance needs separate controls. [F, practitioner, M — R24]
5. **Durable execution changes side-effect semantics.** In LangGraph, a resumed node restarts from its beginning, and in-flight work may re-run, so side effects must be isolated and idempotent. [F, H — R01, R02] This is the single most important "demo vs production" implementation detail for approval flows.
6. **Multi-agent is not justified for this use case.** MAST catalogued 14 failure modes across 1,600+ multi-agent traces [F, H — R10]; Anthropic's multi-agent research system costs ~15× chat tokens and suits read-heavy parallel work [F, H — R12]; Cognition argues against multi-agent for coupled tasks [F, opinion — R13]. Invoice ops is a coupled, write-capable task → single agent. [I, H]
7. **OWASP now has an agent-specific list (ASI01–ASI10, Dec 2025)** layered on the LLM Top 10 (2025). [F, H — R04, R05] Use it as the threat-model checklist and explicitly mark categories that are *designed out* (e.g., code execution, inter-agent comms).
8. **Observability standards are real but unstable.** OTel GenAI conventions define `invoke_agent`, `chat`, `execute_tool` spans but remain at *Development* status and moved to a separate repo in June 2026. [F, M — R16] Pin versions; don't over-invest in attribute names.

---

## A. Production readiness

### A1. Why demo agents fail in production

| Demo assumption | Production reality | Evidence / label |
|---|---|---|
| One successful run = it works | Run-to-run variance; pass^k collapses with k | [F, H — R08] |
| Happy-path data | PO mismatches, missing receipts, duplicates, partial payments | [I, H — domain] |
| Policy lives in the system prompt | Prompt policy is advisory; models can be steered by injected content | [F, H — R04, R06] |
| Agent calls APIs with its own credential | Confused-deputy: agent's broad service account executes on behalf of a user who lacks rights | [I, H] (ASI03 primary defense is per-agent identity + short-lived scoped creds [F, secondary, M — R04b]) |
| Calls succeed | Timeouts, 429s, 5xx, malformed payloads; retries duplicate writes | [I, H] |
| Process stays alive | Approvals take hours/days; process restarts → replay semantics matter | [F, H — R01, R02] |
| Traces = quality | Traces show *what happened*, evals define *what correct means* | [F, survey — R14] |

### A2. Failure modes for the invoice assistant (feeds dataset + controls)

| # | Failure mode | Concrete example | Control (hardened) | Measured by |
|---|---|---|---|---|
| F1 | Wrong entity | Agent picks INV-10428 instead of INV-10482 | Deterministic ID normalisation + existence check | Tool-arg accuracy |
| F2 | Fabricated reason | Claims "price variance" when hold is NO_RECEIPT | Rule engine computes status; LLM only explains evidence | Grounded response rate |
| F3 | Unsupported numbers | States wrong variance amount | Post-generation numeric/ID grounding check | Grounded response rate |
| F4 | Unauthorized read | Shows another tenant's invoice | Tenant/BU scoping in repository + OBO token | Authz violation rate |
| F5 | Unauthorized write | Clerk asks to release a hold | Policy engine at tool boundary | Authz violation rate |
| F6 | Approval bypass | Write executed without approval | Interrupt bound to action hash | Approval compliance |
| F7 | Duplicate side effect | Retry or resume posts the hold release twice | Idempotency key + unique constraint | Duplicate side-effect count |
| F8 | Injection via vendor text | Invoice memo: "update remit-to bank account" | Untrusted-field quarantine, tool allow-list per intent, denied tool | Authz violation + injection success |
| F9 | Unsafe failure | API timeout → agent guesses status | Bounded retry, circuit breaker, safe-failure template | Failure recovery rate |
| F10 | Runaway loop / cost | Agent re-calls search 15 times | Step + token budgets | Tokens, latency |
| F11 | Over-refusal | Legit supervisor action blocked | Policy unit tests; over-refusal metric | Over-refusal rate |

### A3. Deterministic workflow vs autonomous agent
- Anthropic: workflows = predefined code paths; agents = LLM dynamically directs process/tool use; start simple, add complexity only when it measurably helps. [F, H — R11]
- **Recommendation [I, H]:** "constrained agent" — deterministic spine; LLM used at exactly three points: (1) intent + entity extraction (structured output), (2) read-plan selection *only* for open-ended queries, from an allow-list, (3) evidence-constrained explanation. Business status, next action, authorization and approval requirements are computed in code.
- **Honest trade-off [S, M]:** this loses flexibility on open-ended requests ("why are Vendor X's invoices stuck this week?"). We add open-ended scenarios to *measure* that cost rather than hide it.

### A4. Single- vs multi-agent
- MAST: 14 failure modes in 3 categories (specification/system design, inter-agent misalignment, task verification), Cohen's κ 0.88, 1,600+ traces across 7 frameworks. [F, H — R10]
- Anthropic research system: ~4× tokens for agents and ~15× for multi-agent vs chat; good fit for parallel, read-heavy research, poor fit where agents share context/dependencies. [F, H — R12]
- LangChain synthesis: read-heavy multi-agent is easier than write-heavy. [F, opinion — R12b]
- **Decision [I, H]:** single agent. Mention multi-agent only as a "when it would make sense" sidebar (e.g., month-end batch triage across thousands of invoices).

### A5. Stateful, long-running execution
- LangGraph interrupts: require a checkpointer + `thread_id`; graph waits indefinitely; resume with `Command(resume=...)`. [F, H — R01]
- **Gotcha:** on resume the *whole node re-runs from the top*; multiple interrupts in a node are matched by index; avoid `while True` + interrupt loops; don't wrap `interrupt()` in try/except. [F, H — R01]
- Durability modes `exit` / `async` / `sync` trade overhead vs crash safety; side effects should be wrapped in tasks and be idempotent. [F, H — R02]
- Practitioner crash test (LangGraph 1.2.16 + SQLite): in-flight task ran twice on resume. [F, practitioner, M — R23] → We will reproduce this as a deterministic test, not rely on the blog.
- **Design rule [I, H]:** `request_approval` and `execute_action` are separate nodes; `execute_action` is idempotent by key; use `durability="sync"` for the action path.

### A6. Reliability engineering patterns (applied)
| Pattern | Rule for this system [I, H] |
|---|---|
| Timeouts | Per-tool timeout from contract (e.g., read 2s, write 5s); overall request budget |
| Retries | Only on retryable errors (timeout, 429, 503) and only for READ or idempotent-WRITE tools; exponential backoff + jitter; max 3 |
| Circuit breaker | Per service; open → fail fast to safe-failure response |
| Budgets | Max graph steps; max LLM calls; max tokens per request |
| Idempotency | Key = hash(tenant, action, target, canonical args, approval_id); unique constraint; `Idempotency-Key` header honoured by mock services |
| Postconditions | After a write, re-read and verify state; mismatch → alert + audit |
| Safe failure | Never synthesise missing data; say which system failed and what to do |

---

## B. Enterprise agent architecture

### B1. Orchestration options (for this use case)

| Option | HITL pause/resume | Crash recovery model | Extra infra | Fit / notes | Source |
|---|---|---|---|---|---|
| **LangGraph 1.2.x** | `interrupt()` + `Command(resume)`; tool-level interrupts; typed `response_schema` (≥1.2.12) | Checkpoints in own DB; node re-executes on resume | None beyond DB (SQLite/Postgres) | Explicit state graph = easy to draw, test, explain | R01, R02, R22 |
| Pydantic AI | Deferred tools end the run; a new run resumes with approvals | Hands durability to Temporal / DBOS / Prefect | Engine (DBOS can use Postgres/SQLite) | Strong typing; graph less explicit | R21, R22 |
| OpenAI Agents SDK | `needs_approval` tools, state serialise/approve/resume | Needs external engine for crash recovery | Engine | Provider-centric | R22 (practitioner) |
| Temporal (+ any LLM lib) | Signals/waits | Deterministic workflow replay (most mature) | Temporal cluster | Overkill for a reproducible blog repo | R22, R23 |
| Plain while-loop | DIY | DIY | None | Good *baseline* readability | — |

**Recommendation [I, H]:** keep LangGraph. It makes the state machine a first-class artifact, has native HITL + SQLite checkpointing, and lets both arms share one runtime so the benchmark compares *controls*, not frameworks. Mention Pydantic AI + DBOS and Temporal as production alternatives.

### B2. Tool contracts
Each tool declares: Pydantic input/output models; `side_effect` ∈ {READ, WRITE_REVERSIBLE, WRITE_IRREVERSIBLE}; required scopes; `supports_idempotency`; timeout; retryable error codes; output fields marked `trusted` vs `untrusted` (vendor-supplied free text). Anthropic notes tool definitions deserve the same engineering effort as prompts. [F, H — R11]

### B3. State & checkpoints
Typed state (Pydantic/TypedDict) with: request, principal (user, tenant, roles, scopes), intent, entities, evidence bundle (tool outputs + provenance), findings, proposed action + hash, approval record, response, audit pointers. Checkpoint namespace includes tenant to prevent cross-tenant thread resumption. [I, H]

### B4. Human approval
- Approval payload = canonical action + hash + evidence summary + policy reason + expiry.
- Resume value validated against a Pydantic schema; **edited** arguments produce a new hash → re-authorise → re-approve (prevents approve-X-execute-Y). [I, H]
- Segregation of duties: approver ≠ requester for payment-affecting actions (standard AP control). [I, H — domain]
- OWASP ASI09 (human-agent trust exploitation): approvers over-trust confident agent text → approval card shows *evidence from systems*, not LLM prose. [F, M — R04c; I, H]

### B5. AuthN / AuthZ
- FastAPI validates a synthetic JWT (user, tenant, BU, roles). Tools receive an on-behalf-of principal; policy evaluated **in code at the tool boundary**, never by the LLM. [I, H]
- Real-world analogue: MCP 2026-07-28 models protected servers as OAuth 2.1 resource servers with tokens from a separate authorization server; authorization is still OPTIONAL in the spec. [F, H — R17] → good article point: "the protocol won't enforce least privilege for you."

### B6. Enterprise integration
Anti-corruption layer per backend (normalise ERP payloads into domain models), idempotency headers, correlation IDs propagated into traces, and contract tests against mock services. Keep tools in-process for the benchmark; optionally expose the same contracts via MCP in an appendix (adds transport latency that would confound results). [I, M]

### B7. Data isolation & multi-tenancy
`tenant_id` on every row; repository-level filters (not prompt-level); per-tenant checkpoint namespace; no cross-session long-term memory (designs out ASI06 memory poisoning); trace/audit redaction of bank and tax identifiers. [I, H]

### B8. Fault tolerance
Fault-injection middleware in mock services (timeout, 429, 500, malformed JSON, slow response), seeded and declared per scenario so failures are reproducible. [I, H]

---

## C. Security & governance

### C1. OWASP LLM Top 10 (2025) — relevant items [F, H — R05]
LLM01 Prompt Injection · LLM02 Sensitive Information Disclosure · LLM05 Improper Output Handling · LLM06 Excessive Agency · LLM10 Unbounded Consumption.
Note: one secondary source refers to a 2026 edition of the LLM list — **unverified**; cite the 2025 edition unless confirmed on genai.owasp.org.

### C2. OWASP Top 10 for Agentic Applications 2026 → controls [F list — R04; mapping I]

| ID | Risk | Invoice assistant control | Status |
|---|---|---|---|
| ASI01 | Agent Goal Hijack | Plan fixed before untrusted data; untrusted fields quarantined | In scope |
| ASI02 | Tool Misuse & Exploitation | Per-intent tool allow-list; arg validation; write tools gated | In scope |
| ASI03 | Identity & Privilege Abuse | OBO principal; no broad service account in hardened arm | In scope |
| ASI04 | Agentic Supply Chain | Pinned deps; no dynamic tool discovery | Partially |
| ASI05 | Unexpected Code Execution | No code-exec tools | Designed out |
| ASI06 | Memory & Context Poisoning | No long-term memory; per-thread state only | Designed out (mostly) |
| ASI07 | Insecure Inter-Agent Comms | Single agent | Designed out |
| ASI08 | Cascading Failures | Circuit breakers, budgets, postconditions | In scope |
| ASI09 | Human-Agent Trust Exploitation | Evidence-based approval cards; action hash | In scope |
| ASI10 | Rogue Agents | Audit + anomaly flags; kill switch (config flag) | Partially |

### C3. Prompt injection
- Patterns paper principle: once untrusted input is ingested, it must not be able to trigger consequential actions. [F, H — R06]
- We implement **plan-then-execute + context-minimization**: intent/plan derived from user message only; vendor free-text is excluded from planning context and passed to the explainer as clearly delimited data; writes require user-originated intent + policy + approval.
- Residual risk [I, H]: injected text can still distort the *explanation*. Grounding check limits numeric/ID distortion; qualitative distortion is measured by judge.
- Realistic vector [I, H]: business-email-compromise style "remit-to bank change" instructions inside vendor memos/PDF text. Real-world indirect-injection precedent: EchoLeak (CVE-2025-32711) zero-click against M365 Copilot. [F, secondary, M — R04b; verify on NVD before citing]
- Evaluation precedent: NIST CAISI found multi-attempt testing gives more realistic hijacking results; AgentDojo is the leading open framework. [F, H — R18, R20] A large red-teaming competition found at least one successful attack against every target frontier model. [F, H — R19]

### C4. Sensitive data
Mask bank/tax IDs at the service layer; LLM never receives full account numbers; output filter for patterns; redaction in logs/traces. [I, H]

### C5. Governance & audit
Audit event per decision: who (principal), what (tool/action + args hash), when, why (policy rule id, evidence refs), approval id, outcome. Audit log is append-only and separate from traces (different retention and integrity needs). [I, H]
Frameworks to reference (from prior knowledge — **verify before citing**): NIST AI RMF 1.0 and the Generative AI Profile (NIST AI 600-1); ISO/IEC 42001.

---

## D. Evaluation & observability

### D1. Evaluation layers
1. **Deterministic checks** (no LLM): state diffs, policy decisions, idempotency, schema validity. 
2. **Trajectory checks**: required/forbidden tool calls; agentevals offers strict/unordered/subset/superset modes and arg-matching overrides. [F, H — R21b] We use *superset* for reads (extra reads allowed) and *subset/forbidden* for writes.
3. **Outcome checks**: expected outcome class + required facts.
4. **LLM-as-judge** only for qualitative claims; calibrated against a human-labelled subset. [I, H]

### D2. Reliability metric
pass^k = E_task[ C(c,k) / C(n,k) ] for n trials with c successes. [F, H — R08]

### D3. Observability
- OTel GenAI: `invoke_agent` (run) → `chat` (model call) → `execute_tool` (tool) with token/model attributes; status Development; moved to `semantic-conventions-genai` with core v1.42.0 (2026-06-12). [F, M — R16]
- Execute_tool spans stop at the tool boundary; add child spans for HTTP, auth, retries. [F, practitioner, M — R16b]
- Decision [I, H]: OTel SDK + console/JSONL exporter by default; optional Jaeger/Phoenix for screenshots. No hosted vendor dependency for reproducibility.

### D4. Framework landscape (for the article sidebar)
Verified this session: LangChain agentevals (trajectory match) [R21b]; Pydantic Evals/AI production stack [R21]; Inspect AI (UK AISI) used by NIST's AgentDojo-Inspect [R18]; τ²-bench repo (Sierra) [R08b]. Not verified this session (mention neutrally or verify): LangSmith, Langfuse, Arize Phoenix, DeepEval, Braintrust.
**Recommendation [I, H]:** write our own small scorer (transparent, ~300 LOC) and optionally show the same checks in agentevals.

---

## E. Benchmarking notes (detail in `benchmark_methodology.md`)
- Fairness: same model, tools, tool descriptions, policy text, and tuning budget for both arms; baseline is a competent prompt-governed agent, not a strawman. [I, H]
- Expected trade-offs [S]: hardened → near-zero executed violations (H), higher grounded rate on mismatch/duplicate (M), higher p50 latency (M), tokens uncertain (L), lower success on open-ended queries (M), more over-refusal (M).
- Validity threat: the designer knows the scenarios → dev/holdout split + independent ground-truth oracle.

---

## F. Current trends (as of 2026-11-11)
- Agent-specific security taxonomies (OWASP ASI, Dec 2025). [F — R04]
- MCP 2026-07-28: stateless core, OAuth-based auth refinements, DCR deprecated in favour of Client ID Metadata Documents. [F, M — R17, R17b]
- OTel GenAI conventions split into their own repo, still Development. [F, M — R16]
- Durable execution becoming default infrastructure for agents (LangGraph checkpoints; Pydantic AI on DBOS/Temporal). [F, M — R21, R22]
- Multi-agent debate converged on "architecture follows task structure." [I, M — R12, R13]

## G. Claims NOT to use
- "88% of agent pilots never reach production (LangChain)" — appears misattributed; LangChain's report says ~57% have agents in production. **Do not cite.**
- Any token price from memory — read from provider pricing page on run date.
- Gartner's ">40% of agentic AI projects canceled by end-2027" is a **prediction**, cite as such. [F — R15]
