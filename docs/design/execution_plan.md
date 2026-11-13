# Execution Plan

## 1. Phases and exit criteria

| Phase | Scope | Exit criteria | Gate |
|---|---|---|---|
| ✅ P0 Setup | Repo, uv env, pin versions (check PyPI on day 1), pin the single M2 model ID (confirm temperature, structured-output, tool-calling and caching support), record prices with source URL/date | `uv lock` committed; `config/models.yaml`, `config/prices.yaml` filled | — |
| ✅ P1 Domain & services | Domain models, rule engine, policy engine, next-action table, mock services with fault/latency injection, JWT auth, idempotent action log | T1 + T3 green; coverage ≥85% on domain/security | — |
| ✅ P2 Data | World + scenario generator, independent oracle, validators, dev/holdout freeze | Validation report clean; oracle = rule engine 100%; MANIFEST hashes | **Approval #2: dataset review** |
| ✅ P3 Baseline | `create_agent` baseline, prompt, broad credential, tracing | Runs end-to-end on 10 dev scenarios | — |
| ✅ P4 Hardened | Graph nodes, approval interrupt, idempotent execute, grounding check, budgets, untrusted quarantine; A1 ablation | T2 green incl. crash/resume & edited-args tests | — |
| ✅ P5 Harness & scoring (judge replaced by deterministic grounding + human review) | Runner, scripted approver, scorers, judge + calibration set, stats, report | T4 green (golden traces); judge κ reported | — |
| P6 Pilot | 10 scenarios × k=1 × B0/H × M2 | Measured cost/run, time/run, error rates → full-run estimate | **Approval #3: budget** |
| P7 Benchmark | Tuning on 20-scenario dev subset (k=1, ≤3 revisions/arm) → freeze → B0/H on all 100 × k=3; A1 on 28 authz scenarios × k=3 | Report generated; hypotheses scored | — |
| P8 Article | Draft from outline using only measured results + cited sources | Draft for review | **Approval #4: draft** |

## 2. Project structure

```
invoice-agent-bench/
├── pyproject.toml  uv.lock  Makefile  README.md  .env.example
├── config/
│   ├── settings.yaml        # budgets, timeouts, retry policy, durability
│   ├── policies.yaml        # authz + approval rules (rule IDs)
│   ├── tolerances.yaml      # synthetic AP policy
│   ├── latency_profile.yaml # per-tool seeded latency
│   ├── models.yaml          # provider, model ID, decoding params
│   └── prices.yaml          # price per token type + source URL + date
├── src/invoice_bench/
│   ├── domain/        models.py rules.py duplicates.py next_action.py
│   ├── services/      app.py invoices.py purchase_orders.py receipts.py vendors.py payments.py faults.py latency.py
│   ├── tools/         contracts.py registry.py client.py enforcement.py
│   ├── security/      auth.py policy.py masking.py untrusted.py
│   ├── llm/           factory.py fake.py
│   ├── agents/
│   │   ├── baseline/  agent.py prompt.py
│   │   └── hardened/  state.py graph.py approval.py idempotency.py grounding.py nodes/*.py
│   ├── observability/ tracing.py logging.py audit.py
│   ├── api/           app.py routes.py sessions.py
│   ├── data/          generate.py templates/ paraphrases/ injections/ oracle.py validate.py
│   └── bench/         run.py approver_sim.py scorers/*.py judge.py stats.py report.py
├── tests/  unit/ property/ graph/ scorers/ llm/   (llm/ marked @pytest.mark.llm)
├── data/v1/  world.sqlite  scenarios_dev.jsonl  scenarios_holdout.jsonl  MANIFEST.json  golden_traces/
├── runs/  (gitignored; manifests + redacted JSONL exported to results/)
├── results/  reports/  docs/diagrams/
```

## 3. Dependencies (pin exact versions in P0; ranges are intent)

| Group | Packages |
|---|---|
| Runtime | python 3.12, fastapi, uvicorn, pydantic ≥2, pydantic-settings, langgraph 1.2.x, langgraph-checkpoint-sqlite, langchain-core, langchain (for `create_agent`), provider packages (e.g. langchain-anthropic, langchain-openai), httpx, pyjwt[crypto], tenacity, structlog, opentelemetry-sdk, opentelemetry-exporter-otlp (optional), pyyaml |
| Test | pytest, pytest-asyncio, hypothesis, pytest-cov |
| Analysis | numpy, pandas, scipy, matplotlib |
| Dev | uv, ruff, mypy |
| Optional | Jaeger or Arize Phoenix (trace UI screenshots), agentevals (cross-check trajectory scoring) |

New vs proposed stack: **PyJWT, tenacity, structlog, OpenTelemetry, hypothesis, httpx, analysis libs, uv** — each justified in `architecture_proposal.md` §7.

## 4. Commands (planned)

```bash
uv sync
uv run pytest -m "not llm" -q                                   # T1–T4, offline
uv run python -m invoice_bench.data.generate --seed 20261111 --out data/v1
uv run python -m invoice_bench.data.validate data/v1             # schema, FK, oracle==engine, hashes
uv run uvicorn invoice_bench.api.app:app --reload                # manual exploration
uv run python -m invoice_bench.bench.run --arm baseline --model m1 --split dev --trials 1 --limit 10   # pilot
uv run python -m invoice_bench.bench.run --arm hardened --model m1 --split dev --trials 5
uv run python -m invoice_bench.bench.run --arm ablation_a1 --model m1 --split dev --trials 5
uv run python -m invoice_bench.bench.score runs/<run_id>
uv run python -m invoice_bench.bench.report runs/<b0> runs/<h> runs/<a1> --out reports/dev
make reproduce                                                   # full pipeline from seed
```

## 5. Benchmark execution plan
1. Pilot (P6): 10 stratified dev scenarios, k=1, B0 + H, M2 → measure tokens/run, latency, infra error rate.
2. Projected total = ~824 runs × measured mean tokens/run (+20% margin), checked against `TOKEN_BUDGET_TOTAL`; present for approval.
3. Tuning on the 20-scenario dev subset (k=1) → design freeze (tag `v1-freeze`).
4. Final runs: B0 + H on dev + holdout (100 × k=3); A1 on 28 authz scenarios × k=3. Replay cache on for all re-scoring.
5. Concurrency capped to respect provider limits; arms interleaved; all runs within a short window to reduce provider drift.
6. Score → report → hypothesis scorecard → threats to validity.

## 6. Risks and assumptions

| # | Risk / assumption | Impact | Mitigation |
|---|---|---|---|
| R1 | Model/provider behaviour drifts between runs | Results non-comparable | Pin model IDs; run arms interleaved in one window; record dates |
| R2 | LangGraph API changes within 1.2.x | Rework | Pin exact version; wrap interrupt/resume behind our own module |
| R3 | OTel GenAI attributes change (Development status) | Trace schema churn | Isolate attribute names in `tracing.py`; pin SDK |
| R4 | Designer overfits hardened arm to known scenarios | Inflated results | Holdout with unseen paraphrases/templates; equal tuning budget |
| R5 | Baseline perceived as strawman | Credibility | Competent prompt, same tools; publish baseline prompt; A1 ablation; disclose D4/D5 |
| R6 | LLM judge bias | Grounding metric unreliable | Deterministic grounding first; κ calibration; drop judge if κ < 0.6 |
| R7 | Token overrun | Budget | Hard ceiling in runner; pilot gate; A1 already reduced to 28 scenarios; can drop A1 entirely |
| R10 | Single small model → "a better model would fix it" critique | Credibility | State scope explicitly; optional 28-run k=1 frontier spot-check on safety scenarios (only if you approve) |
| R8 | Synthetic data too clean | Overstated success | Background noise records, near-duplicates, boundary cases, paraphrases |
| R9 | 100 scenarios underpowered for small effects | Over-reading noise | Report CIs; label <~10 pp differences inconclusive |
| A1 | Assumes reader can run a laptop + API keys for ≥1 provider | Reproducibility scope | Provide recorded-replay mode to reproduce scoring without API spend |
| A2 | Assumes single-turn + scripted approval represents the core risk | External validity | State explicitly as limitation |
| A3 | Assumes in-process HTTP mocks approximate enterprise API semantics | Latency realism | Seeded latency profile; disclose |
