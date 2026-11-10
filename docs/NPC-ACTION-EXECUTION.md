# NPC action execution, recovery, and goal progress

The symbolic planner remains read-only. The world driver supplies a successful plan's
ordered action IDs and explicitly selects each step. The executor rechecks live
preconditions and never chooses an NPC's intent or replans autonomously.

## One-tick compatibility path

`ActionExecutionLedger.execute` preserves the original one-shot interface. It
validates the selected plan step, applies declared add/delete effects and resource
costs only when live preconditions and balances permit, and writes an immutable
`npc_action_execution` event. Stable execution IDs are idempotent; conflicting
reuse is rejected.

## Multi-tick actions

Use `start`, `advance`, and `cancel` for actions with duration:

- `ActionExecutionPolicy.duration_ticks` sets the number of advances required.
- `start` checks preconditions and reserves the declared resource costs. Reserved
  resources remain in the caller's balance but cannot be reserved by another
  active action in the same ledger.
- `advance` records progress. Preconditions are checked again on every tick.
  Effects and resource deductions occur only when the final tick completes.
- An interruption or changed preconditions finalizes the action without effects
  or spending and releases its reservation.
- `cancel` explicitly ends an active action and releases its reservation.
- The caller decides whether to replan after a blocked, interrupted, or cancelled
  action; this layer does not silently alter the approved plan.

Every start, progress tick, and terminal result is written to the shared world
event journal. The world event journal must be checkpointed alongside this ledger.

## Persistence and recovery

`to_json` / `to_snapshot` produce a canonical versioned snapshot containing
completed execution records and active progress. Restore with
`ActionExecutionLedger.from_json(planner, policies, restored_events, payload)`
or `from_snapshot`. Restoring verifies action IDs, plan step selection, progress
bounds, duplicate IDs, and the existence of corresponding journal events. An
active action resumes from its stored progress and keeps its resource reservation.

The snapshot does not duplicate the world event journal or world facts/resource
balances. `SimulationWorldCheckpoint.capture(..., action_executions=ledger,
action_world_facts=facts, action_resources=resources)` stores all four together.
Restore the composite checkpoint, then call
`restored.restore_action_execution_ledger(planner, policies)` to rebind the
saved execution state to runtime action definitions. The restored simulation
exposes `action_world_facts` and `action_resources` as mutable state for the
resumed ledger. Checkpoint validation rejects future actions, missing owners,
and mismatched or absent journal events.

## Goal progress

A policy may declare `goal_progress=(("goal-id", 0.1), ...)`. When the action
completes, the ledger applies the increments to the supplied `GoalBook`, capped
at 1.0. Interrupted and cancelled actions do not advance goals. Goal IDs must
exist in that book. The caller remains responsible for choosing meaningful,
evidence-based action-to-goal mappings.

Tests: `tests/test_action_execution.py`.