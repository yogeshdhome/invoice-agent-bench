SEED ?= 20261111
DATA ?= data/v1

.PHONY: setup test data validate review reproduce-data
setup:            ## install pinned env (P0)
	uv sync --group dev --extra agent --extra analysis
test:             ## offline deterministic suite (T1-T4); no API keys needed
	uv run pytest -m "not llm"
data:             ## generate world + 100 scenarios
	uv run python -m invoice_bench.data.generate --seed $(SEED) --out $(DATA)
validate:         ## schema, FK, oracle==engine, synthetic-only, leakage
	uv run python -m invoice_bench.data.validate $(DATA)
review:           ## dataset review pack -> docs/dataset_review.md
	uv run python -m invoice_bench.data.review $(DATA)
reproduce-data: data validate review
	@cat $(DATA)/MANIFEST.json | grep world_dump_sha256

# ---- P3-P5 (agents, harness, scoring) ----
.PHONY: dry-run check-model pilot bench-dev bench-final report
dry-run:          ## offline: all arms x 100 scenarios with a heuristic fake model (pipeline check; scores meaningless)
	uv run python -m invoice_bench.bench.run --dry-run --arm all --split all --trials 1 --out runs/dry --concurrency 8 --no-latency
	uv run python -m invoice_bench.bench.report runs/dry
check-model:      ## step 0: zero-token endpoint/parameter check; step 1: ~1-2k tokens of live calls
	uv run python -m invoice_bench.bench.check_model
PILOT_TAG ?= p2
pilot: check-model ## 11 scenarios x baseline+hardened x k=1 (~22 runs). Needs OPENROUTER_API_KEY. New PILOT_TAG each time
	uv run python -m invoice_bench.bench.run --pilot --arm baseline --trials 1 --out runs/pilot_$(PILOT_TAG)_b
	uv run python -m invoice_bench.bench.run --pilot --arm hardened --trials 1 --out runs/pilot_$(PILOT_TAG)_h
	uv run python -m invoice_bench.bench.report runs/pilot_$(PILOT_TAG)_b runs/pilot_$(PILOT_TAG)_h --out runs/pilot_$(PILOT_TAG)_report
TUNE_TAG ?= t1
tune: check-model ## final tuning round: ~21 stratified dev scenarios (not the pilot ones) x k=1, both arms
	uv run python -m invoice_bench.bench.run --arm bh --split dev --tune-subset --trials 1 --out runs/tune_$(TUNE_TAG)
	uv run python -m invoice_bench.bench.report runs/tune_$(TUNE_TAG) --out runs/tune_$(TUNE_TAG)_report
bench-final: check-model ## frozen design: B0+H on all 100 x k=3 (interleaved) + A1 on the 28 authz scenarios x k=3
	uv run python -m invoice_bench.bench.run --arm bh --split all --trials 3 --out runs/final_bh
	uv run python -m invoice_bench.bench.run --arm ablation_a1 --split all --categories access_violation,approval_write,prompt_injection --trials 3 --out runs/final_a1
	uv run python -m invoice_bench.bench.report runs/final_bh runs/final_a1 --out runs/final_report

# ---- Published results (no tokens) ----
.PHONY: results figures diagrams
results:          ## re-score the published raw runs with the frozen scorer, then apply adjudication
	uv run python -m invoice_bench.bench.report results/final/baseline_hardened results/final/ablation_a1 --out results/final/report
	uv run python -m invoice_bench.bench.adjudicate results/final/report/scores.jsonl docs/adjudication_v1.yaml
figures: results  ## regenerate the article charts (needs: uv sync --extra analysis)
	uv run python -m invoice_bench.bench.figures results/final/report/scores.jsonl docs/adjudication_v1.yaml results/final/figures
diagrams:         ## render architecture/workflow diagrams (needs Graphviz `dot` on PATH)
	dot -Tpng -Gdpi=200 docs/diagrams/architecture.dot -o results/final/figures/fig0a_architecture.png
	dot -Tpng -Gdpi=200 docs/diagrams/workflow.dot -o results/final/figures/fig0b_workflow.png
