# NPC action outcome evaluation

`ActionPlanEvaluationLedger` compares an immutable terminal execution record
with the authored `PlanningAction` effects and `ActionExecutionPolicy` resource
costs and duration. It requires the same execution ledger and authoritative
world-event journal.

Call `evaluate(execution_id)` after an action reaches a terminal state. For automatic
integration, construct `NPCActionReplanningCoordinator(..., evaluations=ledger)`;
each terminal step returned by `advance()` then carries its
`NPCActionEvaluation` in `NPCActionProgression.evaluation`. Intermediate
progress ticks are not evaluated. The
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


## Composite world checkpoint integration

Pass the same evaluation ledger used by the replanning coordinator as
`action_evaluations=...` to `SimulationWorldCheckpoint.capture`, alongside
`action_executions`, `action_world_facts`, `action_resources`, and
`action_replanning`. Capture rejects mismatched execution ledgers, event
journals, or coordinator bindings, and validates every evaluation against its
terminal execution, its `npc_action_evaluated` event, and all evidence event
IDs. Evaluation state cannot be checkpointed without its execution state.

After restoring the world, reconstruct in this order:

1. `restore_action_execution_ledger(planner, policies)`
2. `restore_action_evaluation_ledger(executions)`
3. `restore_action_replanning_coordinator(decisions, executions, evaluations)`

The restored coordinator uses the restored evaluation ledger for subsequent
terminal action steps. Checkpoints created before evaluation persistence remain
valid and simply return no evaluation snapshot.
