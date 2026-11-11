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
## Explicit autonomous replanning

`NPCActionReplanningCoordinator` joins an `NPCDecisionCycle` to the same
`ActionExecutionLedger` and `WorldEventLedger`. The world driver calls
`replan(owner_id, tick, facts, resources, goal_facts, reason=...)` after a
precondition failure, interruption, resource change, or goal-priority change.
If an active execution ID is supplied, the coordinator verifies ownership and
cancels that action first, releasing its reservation while retaining its
terminal journal record.

The coordinator reruns goal ranking against current state, validates the full
plan's cumulative declared resource costs (including active reservations), and
starts the first action of a feasible plan. It does not invent costs or silently
change goal mappings. Because the symbolic planner is resource-agnostic, an
infeasible selected plan is reported as blocked; finding a different
resource-feasible route requires resource constraints to be modeled in the
authored planning actions. Empty plans are reported as already satisfied.
Stable request hashes make identical replan calls idempotent. Every decision is
recorded as `npc_action_replanned` in the shared event journal.

The coordinator itself is a runtime service; the durable action and event
histories remain in the existing composite checkpoint. Recreate the coordinator
after restore using the restored event journal, GoalBook, planner, and
execution ledger. Tests: `tests/test_npc_action_replanning.py`.



Plan progression is handled by `coordinator.advance(execution_id, tick,
facts, resources, goal_facts)`. A completed step starts the next approved step
with a stable per-step execution ID. If the remaining steps no longer satisfy
live preconditions or declared resource costs, the coordinator replans from
the post-action world state. Interrupted actions also trigger a fresh decision
against current goal priorities and facts. The returned
`NPCActionProgression` keeps the terminal result, any newly active step, and
any replacement-plan result distinct.



## Checkpointing replanning history

Pass `action_replanning=coordinator` to
`SimulationWorldCheckpoint.capture` alongside the matching action execution
ledger, world facts, resource balances, and GoalBook. The composite checkpoint
stores the canonical request signatures, decisions, plan revisions, outcomes,
and journal event references. Restore the execution ledger first with
`restore_action_execution_ledger`, rebuild the `NPCDecisionCycle` from the
restored GoalBook and runtime planner, then call
`restore_action_replanning_coordinator(decisions, executions)`. Identical
requests after recovery return the original result without starting duplicate
actions. Checkpoint validation verifies every persisted replan against its
owner, tick, and authoritative `npc_action_replanned` event.


## Goal recovery hand-off

When an abandoned intention becomes viable again, `GoalRecoveryReplanningAdapter.recover_and_replan` performs the lifecycle reopening and calls the same coordinator described above with current world facts, resources, and goal mappings. Pass the superseded active execution ID when applicable so its reservation is released before the replacement plan starts. The planner creates a fresh route; it never resumes the old plan cursor. Completed, interrupted, and cancelled execution records remain in the shared ledger. The lifecycle and replanning snapshots can be checkpointed with the existing world checkpoint so recovery survives restart without duplicate action starts.


## Interrupted plan continuation

An interrupted action remains a terminal historical record; it is never reopened or overwritten. NPCActionReplanningCoordinator.resume_interrupted(execution_id, tick, world_facts, resources, goal_facts) uses the persisted originating replan request to recover the exact plan cursor, then starts a new execution identity for the interrupted action and only the remaining suffix. It requires the interruption tick to have passed, rechecks live action preconditions and cumulative resource feasibility, and refuses to create parallel active work for the same NPC. The deterministic resume identity makes same-tick retries idempotent. Subsequent calls to coordinator.advance continue from the suffix, so previously completed actions are not repeated. If the original replan history is unavailable, the adapter refuses to guess the missing plan cursor and callers must perform a fresh replan instead. The ordinary `advance` interruption path still performs a fresh replan; callers that explicitly want to preserve the old plan cursor can invoke `resume_interrupted` when the interrupted action and remaining suffix are viable. Interrupted plans are recorded with terminal status `replanned`, not `failed`, so transient disruption does not inflate persistent goal-execution failure streaks.
