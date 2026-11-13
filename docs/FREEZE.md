# Design freeze — freeze-v1 (2026-11-12)

After this point only crash fixes are allowed; any other change invalidates the final run.

| Component | Frozen version | Tuning history |
|---|---|---|
| Dataset | v1.2, seed 20261111 | v1.1 supporting facts; v1.2 accepted alternative for read-only vendor-number ambiguity (AM-003/004), approved by author |
| World DB dump SHA-256 | 48b5e59f8a617dfe578824381aa2ebd6c88419420d54496b51f3eaaf31ddd10d | unchanged since v1 |
| scenarios_dev.jsonl SHA-256 (LF) | 25ad9d03529ad46822200910aff2365bbde6d08111fad4b9a8b80c03051c4f13 | |
| scenarios_holdout.jsonl SHA-256 (LF) | 6910f789cc94c98714ed2e4e20a8d12946ef391c7cbe5b17eb37a49becf87778 | holdout never run |
| Baseline (B0) | revision 3 | r1 fetch PO/receipts; r2 approver rules from policy file; r3 retry-once + duplicate search |
| Hardened (H) | revision 2 | r1 action note, open-ended next actions, hide internals; r2 action target vs context IDs, payment amounts |
| A1 ablation | unchanged since P5 | |
| Scorer | v4 | v1 negation/enums/IDs/derived arithmetic; v2 refusal vs scope; v3 rounding, write-requested refusals, markdown; v4 truncated-search violations, negated status, disambiguation precedence, accepted alternatives |
| Model route | OpenRouter anthropic/claude-haiku-5.5, pinned upstream anthropic, no fallbacks, require_parameters | temperature unsupported -> null; reasoning effort none (probe: enabled:false still thought) |
| Budgets | 8 / 5 LLM calls, 800 output tokens per call, 48k input tokens per run | 24k cap raised after p2 |

Verification run t2 (21 dev scenarios, k=1, scorer v4): baseline 15/21, hardened 21/21. Every remaining baseline failure was
reviewed by hand and is genuine agent behaviour (4 out-of-scope data exposures via the service account, 1 arithmetic slip,
1 exhausted retry budget).
