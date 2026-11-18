# Article Outline

**Title:** Your AI Agent Works in a Demo. But Can You Trust It in Production? Building and Benchmarking Production-Ready Enterprise AI Agents
**Audience:** senior AI engineers, architects, tech leads · **Target length:** ~5,000–6,000 words + code + 6 figures · **Voice:** architect-to-engineer, first person, precise, no hype.
**Model scope:** one small/cheap model (M2) — frame as "the model you can actually afford to run at enterprise volume"; no claims about frontier models.
**Guardrails:** no claim of real deployment; every number either from our benchmark (with CI) or a cited source; survey/prediction figures labelled as such; results sections written only after the benchmark runs.

| # | Section | Objective | Content & evidence | Figures / code | Words |
|---|---|---|---|---|---|
| 1 | **Cold open: the demo that passed** | Hook with a relatable failure chain | INV-10482 demo answer looks perfect. Then four replays: PO API times out → agent guesses; 2.01% variance mis-called "within tolerance"; clerk says "just release it" → it does; vendor memo says "remit-to bank changed" → agent tries `update_vendor` | Side-by-side transcript snippets (synthetic) | 450 |
| 2 | **Why production is a different problem** | Reframe from "smarter model" to "system properties" | pass^k and consistency (τ-bench); evaluation gap (LangChain survey, labelled survey); Gartner cancellation *prediction*; confused deputy; replay side effects | Fig 1: failure-mode → control matrix | 650 |
| 3 | **Design principle: LLM proposes, code disposes** | State the thesis and its cost | Workflows vs agents (Anthropic); why single agent (MAST, Cognition vs Anthropic token costs); where the LLM is allowed to decide (3 points) and where it isn't | Fig 2: "decision ownership" diagram | 550 |
| 4 | **Architecture** | Make the design concrete | Components, state machine, trust boundaries (trusted user intent vs untrusted vendor text) | Fig 3: component diagram; Fig 4: state machine | 500 |
| 5 | **Implementation deep dives** | The engineering meat | 5.1 Typed tool contracts with side-effect class · 5.2 On-behalf-of authz at tool boundary · 5.3 Approval bound to action hash (+ edited-args re-approval) · 5.4 The resume gotcha: nodes re-run from the top → idempotent execute node · 5.5 Retries only where safe; circuit breaker; safe failure · 5.6 Untrusted fields & plan-then-execute (and what it *doesn't* protect: arguments) · 5.7 Grounding check · 5.8 OTel spans + audit ≠ trace | Code: `ToolContract`, `policy.decide()`, approval node with `interrupt()`, idempotency key function, grounding check (each ≤25 lines); Fig 5: approval sequence | 1,500 |
| 6 | **Test design** | Show how correctness is defined | Synthetic world; revised scenario taxonomy and why (no writes/injection in naive sets); oracle independence; dev/holdout | Table: distribution; snippet: one scenario JSON | 500 |
| 7 | **Benchmark method** | Make results trustworthy | Arms (B0, H, A1), fairness controls, metric definitions, blocked-is-correct scoring, deterministic vs statistical tiers, CIs | Table: metric definitions (condensed) | 550 |
| 8 | **Results** | Report honestly | Headline table; per-category heatmap; pass^k curves; latency/cost; injection panel; hypothesis scorecard. **Placeholders until run** | Figs 6–8 | 600 |
| 9 | **Trade-offs** | Where hardening costs | Latency, flexibility on open-ended queries, over-refusal, code size, approval friction; when the baseline is "good enough" (read-only, internal, low-risk) | Trade-off scatter | 400 |
| 10 | **Engineering lessons** | Portable takeaways | 7–8 lessons, each tied to a measured result (not opinions) | — | 350 |
| 11 | **Reproduce it** | Credibility | Repo, `make reproduce`, dataset hash, model IDs, cost of a full run | Command block | 150 |
| — | Sidebars | Optional | "When multi-agent would make sense"; "Same tools over MCP (2026-07-28 auth model)"; "OWASP ASI mapping" | Table | — |

## Key research findings to weave in
- pass^k definition and the consistency collapse (R08).
- Workflows vs agents; start simple (R11).
- Multi-agent token cost and fit (R12, R13, R10).
- Six injection-resistant patterns + residual argument risk (R06, R24).
- LangGraph resume re-executes the node; durability modes (R01, R02).
- OWASP ASI01–ASI10 and LLM06 Excessive Agency (R04, R05).
- Observability adopted far more than evals (R14, survey).
- NIST: multi-attempt attack evaluation; no frontier model fully robust (R18, R19).
- MCP authorization is OPTIONAL in spec → enforcement is your job (R17).

## Candidate lessons (to confirm or drop after results)
1. Put authorization where the side effect happens, not in the prompt.
2. Approve the action hash, not the conversation.
3. Assume every node runs twice.
4. Retry is a write-safety decision, not a resilience setting.
5. Measure pass^k; averages flatter agents.
6. Untrusted text can't choose verbs — but it can still shape nouns.
7. The cheapest control (identity) may buy most of the safety (pending A1).
8. Hardening has a flexibility tax; measure it instead of denying it.
