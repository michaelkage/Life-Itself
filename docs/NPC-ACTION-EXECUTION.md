# Replay-safe NPC action execution

The symbolic planner remains read-only. It returns an ordered sequence of action
IDs; the world driver then submits one selected step to
`ActionExecutionLedger.execute`. Execution is not an implicit side effect of
planning.

## Execution contract

- The caller supplies the approved plan's complete action-ID tuple and the
  selected zero-based step. The action ID must match that plan step.
- The executor rechecks the action's preconditions against current world facts.
  A plan that has become stale is blocked rather than blindly applied.
- Optional `ActionExecutionPolicy` records explicit resource costs by action.
  Missing resource balances count as zero; insufficient resources block the
  action without consuming anything.
- The caller may supply an explicit interruption reason. Interrupted actions
  are journaled but do not apply effects or spend resources.
- A completed action applies declared add/delete effects and resource costs
  atomically within the caller-owned mutable fact set and resource dictionary.
- Each execution emits an immutable `npc_action_execution` world event with
  owner, action, status, and reason.
- Stable execution IDs are idempotent. Reusing an ID with different owner,
  tick, action, plan step, world facts, resources, or interruption is rejected.

## Example

```python
from simreality import (
    ActionExecutionLedger, ActionExecutionPolicy,
    DeterministicPlanner, PlanningAction, WorldEventLedger,
)

planner = DeterministicPlanner((
    PlanningAction("buy-tools", frozenset({"at-shop"}),
                   frozenset({"has-tools"})),
    PlanningAction("repair-bike", frozenset({"has-tools"}),
                   frozenset({"bike-fixed"})),
))
events = WorldEventLedger()
executor = ActionExecutionLedger(
    planner, (ActionExecutionPolicy("buy-tools", (("cash", 5.0),)),), events
)

# Supplied by the planner's successful PlanResult.
plan = ("buy-tools", "repair-bike")
facts = {"at-shop"}
resources = {"cash": 12.0}

first = executor.execute(
    "tick-10:step-0", "npc-1", 10, plan[0], facts, resources,
    plan_actions=plan, action_index=0,
)
if first.status == "completed":
    second = executor.execute(
        "tick-11:step-1", "npc-1", 11, plan[1], facts, resources,
        plan_actions=plan, action_index=1,
    )
```

The executor does not invent resource prices, decide whether a disruption
occurred, retry blocked actions, choose a new goal, or infer an NPC's intent.
The world driver supplies those facts and decides whether to replan. This first
slice records execution in the shared event journal; durable action-execution
snapshot/checkpoint integration and C++ runtime integration remain follow-up
work. Tests are in `tests/test_action_execution.py`.
