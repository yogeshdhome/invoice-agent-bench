# Benchmark report

| Metric | ablation_a1 | baseline | hardened |
|---|---|---|---|
| Strict task success | 66.7% [56.1%–75.8%] (n=84) | 74.0% [68.8%–78.6%] (n=300) | 95.7% [92.7%–97.5%] (n=300) |
| pass^1 | 66.7% | 74.0% | 95.7% |
| pass^2 | 57.1% | 69.3% | 94.3% |
| pass^3 | 50.0% | 67.0% | 94.0% |
| Tool selection accuracy | 89.3% [80.9%–94.3%] (n=84) | 88.7% [84.6%–91.8%] (n=300) | 100.0% [98.7%–100.0%] (n=300) |
| Tool argument accuracy | 100.0% (n=114) | 100.0% (n=459) | 100.0% (n=507) |
| Grounded response rate | 86.7% [73.8%–93.7%] (n=45) | 74.7% [68.8%–79.8%] (n=237) | 95.8% [92.4%–97.7%] (n=237) |
| Authorization violation rate (executed) | 0.0% [0.0%–4.4%] (n=84) | 7.3% [4.9%–10.9%] (n=300) | 0.0% [0.0%–1.3%] (n=300) |
| Authorization attempt rate | 21.4% | 7.3% | 6.0% |
| Approval compliance | 93.3% (n=15) | 100.0% (n=13) | 100.0% (n=21) |
| Over-refusal rate | 4.4% [1.2%–14.8%] (n=45) | 1.3% [0.4%–3.7%] (n=237) | 0.0% [0.0%–1.6%] (n=237) |
| Failure recovery rate | n/a [n/a–n/a] (n=0) | 70.4% [51.5%–84.1%] (n=27) | 92.6% [76.6%–97.9%] (n=27) |
| Injection success rate | 12.5% [4.3%–31.0%] (n=24) | 12.5% [4.3%–31.0%] (n=24) | 8.3% [2.3%–25.8%] (n=24) |
| Duplicate side effects | 0 | 0 | 0 |
| Latency p50 / p95 (ms) | 5,058 / 8,764 | 4,642 / 8,064 | 4,050 / 6,857 |
| Tokens per run (in / out) | 14,194 / 588 | 13,173 / 525 | 2,385 / 261 |
| LLM calls per run | 3.04 | 2.83 | 1.95 |
| Reasoning tokens per run (expect 0 with effort=none) | 0 | 0 | 0 |
| Cost per run / per successful task (USD) | 0.00171 / 0.00257 | 0.00158 / 0.00214 | 0.00037 / 0.00039 |
| Served by (upstream provider: calls) | unreported: 255 | unreported: 848 | unreported: 586 |
| Agent errors / budget failures | 0 / 0 | 0 / 0 | 0 / 0 |

## Paired deltas vs baseline (scenario-clustered bootstrap, 95% CI)

- hardened − baseline: strict_success 21.7% [14.0%–29.7%], violation -7.3% [-12.7%–-3.0%], over_refusal -1.0% [-2.3%–0.0%]
- ablation_a1 − baseline: strict_success 19.0% [6.0%–34.5%], violation -21.4% [-39.3%–-7.1%], over_refusal 0.0% [-3.6%–3.6%]

## Strict success by category

| Category | ablation_a1 | baseline | hardened |
|---|---|---|---|
| access_violation | 53.3% | 3.3% | 100.0% |
| ambiguous | n/a | 72.2% | 100.0% |
| amount_mismatch | n/a | 78.6% | 92.9% |
| approval_write | 76.7% | 73.3% | 100.0% |
| duplicate | n/a | 75.0% | 100.0% |
| normal | n/a | 100.0% | 100.0% |
| open_ended | n/a | 66.7% | 77.8% |
| payment_status | n/a | 100.0% | 100.0% |
| po_issue | n/a | 90.0% | 86.7% |
| prompt_injection | 70.8% | 70.8% | 91.7% |
| tool_failure | n/a | 70.4% | 92.6% |
