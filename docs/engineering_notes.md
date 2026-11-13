# P3–P5 engineering notes (article material — all observed in this repo, not from external sources)

1. **Reserved config key bit us.** Passing `configurable["run_id"]` made every second `ainvoke` on the same LangGraph
   thread a silent no-op (no error, previous state returned). Multi-turn sessions in *both* arms would have been broken,
   and single-turn tests would never have shown it. Renamed to `bench_run_id`; regression test added.
   Lesson: test multi-turn against the real runtime, not just node functions.
2. **Approval node re-runs on resume.** The DB write that registers an approval sits *before* `interrupt()`, so it must
   be idempotent (`INSERT OR IGNORE` keyed by action hash). Verified by test.
3. **Crash after side effect.** Simulated a crash inside `execute_action` after the HTTP write succeeded. On resume the node
   re-ran, the second write was an idempotent replay (`Idempotent-Replayed: true`), and the action log holds one row.
4. **Edited approvals change the hash.** An approver editing the PO number produced a second approval card with a new hash;
   the original approval could not authorise the edited action.
5. **"Not found or no access" is deliberately ambiguous.** The hardened arm cannot (and should not) tell a cross-tenant ID
   from a nonexistent one. The scorer accepts that response for both BLOCKED and CLARIFY expectations — documented.
6. **Scorer validity fixes before any tokens were spent:** classifier precedence (not-found before blocked) and dataset v1.1
   (invoice total / payment id moved from required to supporting facts because the questions don't ask for them).
7. **Token shape (estimate, to be measured in the pilot):** baseline ≈ 0.9k system prompt + 1.25k tool schemas re-sent on
   every loop step; hardened sends no tool schemas and makes ≤3 LLM calls. Expect H5 (fewer tokens for H) to hold, but
   verify — evidence JSON for the explainer is not small.
