# NPC action outcome evaluation

`ActionPlanEvaluationLedger` compares an immutable terminal execution record
with the authored `PlanningAction` effects and `ActionExecutionPolicy` resource
costs and duration. It requires the same execution ledger and authoritative
world-event journal.

Call `evaluate(execution_id)` after an action reaches a terminal state. The
result records expected and observed fact additions/deletions, missing expected
effects, unexpected additions, resource deltas, elapsed ticks, deviation flags,
and exact journal evidence IDs. Cancelled, interrupted, and failed executions
are evaluated as non-successes; no intended effects are credited to them.
Repeated evaluation of one execution is idempotent.

The learning projection maintains a bounded exponential reliability estimate
per action. It begins at 0.5, updates only from terminal evidence, and is exposed
only after `learning_min_samples` observations (default 3). It is descriptive
data for future decision policies; it does not rewrite planner costs, plans,
historical decisions, or execution records. Tune `learning_rate` and the
minimum sample count explicitly.

Snapshots preserve evaluations and learning state. Restore with
`ActionPlanEvaluationLedger.from_snapshot(executions, events, snapshot)`
after restoring the matching execution ledger and event journal. Evaluations
are validated against terminal records and their `npc_action_evaluated`
journal events.

Tests: `tests/test_action_evaluation.py`.
