# invoice-agent-bench

**Building and benchmarking a production-ready enterprise AI agent.**
Companion repository for the article *"Your AI Agent Works in a Demo. But Can You Trust It in Production?"* *[blog link to be added]*.

Three versions of the same synthetic **Enterprise Invoice Operations Assistant** are run against the same 100 scenarios,
three times each:

| Arm | What it is |
|---|---|
| **Baseline (B0)** | LangGraph's prebuilt tool-calling agent. Policy in the prompt, tools on a broad service account, approval asked for in chat |
| **Identity-only (A1)** | B0, but tools run with the *user's* token and a policy engine can refuse a call |
| **Hardened (H)** | A LangGraph state machine: the LLM extracts intent and explains evidence; code does everything else — rules, authorisation, hash-bound approval, idempotent execution, grounding checks |

> All data is synthetic. Nothing here has been deployed in a real enterprise. The model under test (Claude Haiku 5.5) and the
> AI assistant that helped write this code are both Anthropic products.

## Results (freeze-v1, run 2026-11-13)

99 scenarios × 3 trials per arm (scenario AP-009 excluded for a label defect; see `docs/results.md`).

| | Baseline (B0) | Hardened (H) |
|---|---:|---:|
| Strict task success — frozen scorer (primary) | 74.7% | 95.6% |
| Strict task success — after adjudication | 78.5% | 97.6% |
| pass^3 (all three trials succeed), adjudicated | 72.7% | 97.0% |
| Holdout only, adjudicated | 78.2% | 93.1% |
| Runs that retrieved unauthorised data into the model's context | 22 / 297 | 0 / 297 |
| …and disclosed it to the user | 6 | 0 |
| Latency p50 / p95 | 4.6 s / 8.1 s | 4.1 s / 6.9 s |
| Tokens per run | 13,698 | 2,646 |
| Cost per successful task | $0.0020 | $0.0004 |

On the 27 authorisation-sensitive scenarios: B0 58% → A1 85% → H 100%. A1 stopped all 18 unauthorised retrievals on its own.
Full analysis, hypothesis scorecard and threats to validity: [`docs/results.md`](docs/results.md).

## Quick start

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/). Graphviz is optional (diagrams only).

```bash
make setup                      # pinned environment (uv sync)
make test                       # 139 offline tests — no API key, no network
make reproduce-data             # regenerate data/v1 from seed 20261111; compare hashes with data/v1/MANIFEST.json
make dry-run                    # all 3 arms x 100 scenarios with an offline fake model (pipeline check only)
```

### Reproduce the published numbers from the raw runs (no tokens)

```bash
uv sync --group dev --extra agent --extra analysis
make results                    # re-score results/final/* with the frozen scorer, then apply docs/adjudication_v1.yaml
make figures                    # regenerate the article's charts into results/final/figures/
make diagrams                   # architecture and workflow diagrams (needs Graphviz `dot`)
```

`tests/results/test_published_results.py` asserts that the raw runs reproduce the headline counts.

### Run the benchmark yourself (costs tokens)

```bash
export OPENROUTER_API_KEY=sk-or-...        # PowerShell: $env:OPENROUTER_API_KEY = "sk-or-..."
export TOKEN_BUDGET_TOTAL=10000000
make check-model                           # zero-token endpoint/parameter check, then ~2k tokens of live calls
make bench-final                           # 684 runs, ~6M tokens, ~$0.75 at the time of writing
```

Model configuration (`config/models.yaml`): `anthropic/claude-haiku-5.5` via OpenRouter, upstream pinned to Anthropic,
`allow_fallbacks: false`, `require_parameters: true`, no temperature (not accepted by the endpoint), `reasoning: {effort: "none"}`,
800 output tokens per call. Prices change; measured per-call cost is recorded in every run.

## Repository map

| Path | Contents |
|---|---|
| `src/invoice_bench/domain/` | Domain models, 3-way-match rule engine, duplicate detection, next-action table, action hashing |
| `src/invoice_bench/security/` | Principals and JWT verification, policy engine, masking, untrusted-text handling |
| `src/invoice_bench/services/` | Mock AP/ERP services (FastAPI): data scoping, idempotent writes, seeded fault and latency injection |
| `src/invoice_bench/tools/` | Shared tool contracts and HTTP client; retries/circuit breaker (H); policy guard (A1) |
| `src/invoice_bench/agents/` | `baseline/` (B0) and `hardened/` (H) |
| `src/invoice_bench/data/` | World generator, scenario templates, independent ground-truth oracle, validator |
| `src/invoice_bench/bench/` | Runner, scripted approver, outcome classifier, scorer, statistics, report, adjudication, figures, model check |
| `config/` | Policies, tolerances, budgets, latency profile, model routing, price table |
| `data/v1/` | Frozen dataset v1.2: `world.sqlite`, `scenarios_{dev,holdout}.jsonl`, `MANIFEST.json` |
| `results/final/` | **Raw final-run logs** (`runs.jsonl` + `MANIFEST.json` per arm), scored report, figures |
| `results/development/` | Raw pilot and tuning runs (dev scenarios only), kept for transparency — see `results/README.md` |
| `docs/results.md` | Final results and analysis |
| `docs/adjudication_v1.yaml` | Every human override of the frozen scorer, with its rationale |
| `docs/FREEZE.md` | What was frozen before the final run, with hashes and tuning history |
| `docs/engineering_notes.md` | Problems found while building the benchmark |
| `docs/design/` | Research notes, requirements, architecture proposal, data plan, methodology, references |
| `docs/diagrams/` | Graphviz sources for the architecture and workflow diagrams |

## What this repository does and does not implement

**Implemented:** user-scoped tool authorisation with a deterministic policy engine; hash-bound approvals with expiry and
segregation of duties; idempotent writes with crash-and-resume tests; per-tool retries and a circuit breaker; deterministic
grounding checks; append-only audit log; OpenTelemetry-style traces; a reproducible benchmark with an independent answer key.

**Not implemented** (needed for production, discussed in the article): an API gateway with full OIDC validation (audience,
revocation, refresh); on-behalf-of token exchange to real enterprise APIs; a durable checkpointer (the harness uses an
in-memory one); re-authorisation and approver-reason validation immediately before execution; secret management;
throughput and load testing; adaptive prompt-injection attacks.

## Limitations

One small model, one provider, one domain, synthetic data; no sampling control (the endpoint rejects `temperature`);
scripted user and approver; a regex-based outcome classifier (about 4% error, quantified in `docs/results.md`); human
adjudication was not blinded and was performed by one reviewer (the AI assistant that helped build the system), then approved
by the author; agents and scorer were tuned on the development scenarios (holdout reported separately).

## Provenance

The final run's manifests record `git_sha: null` (the code was not under git on the machine that ran it). The run is
identified instead by the frozen dataset and configuration recorded in `docs/FREEZE.md` — dataset v1.2,
`scenarios_dev.jsonl` SHA-256 `25ad9d03…`, `scenarios_holdout.jsonl` `6910f789…`, world dump `48b5e59f…` — and by tag
`freeze-v1` on this repository.

## License and citation

Code is released under the MIT License (see `LICENSE`). If you use this benchmark, please cite it using `CITATION.cff`.
