# NPC Decision Cycle

## Purpose

`simreality/npc_autonomy.py` connects two existing engine-independent services:
`GoalBook` chooses an actionable intention, and `DeterministicPlanner` searches
for a bounded least-cost action sequence that could satisfy its desired facts.

## Decision sequence

1. Evaluate goals for the requested NPC and simulation tick.
2. Rank actionable goals by score with stable goal-ID tie-breaking.
3. Try each goal in that order, using only its caller-provided desired facts.
4. If a goal has no mapping or no valid plan, try the next goal deterministically.
5. Return the first feasible proposal; if none is feasible, preserve the highest-ranked failure for diagnosis.

## Important boundaries

- The cycle never executes actions or mutates world facts or goal progress.
- Goal categories and metadata are not interpreted as hidden action rules. The caller
  must explicitly map goal IDs to desired facts.
- Missing mappings, absent goals, and planning failures are represented explicitly. A lower-ranked goal may be selected when higher-ranked goals are not currently feasible.
- A successful symbolic plan is a proposal, not a guarantee that actions remain valid
  when later applied to a changing live world. The simulation coordinator must
  revalidate preconditions before execution.
- The cycle is deterministic for identical goals, world facts, mappings, planner
  actions, and tick. It uses no random numbers and introduces no external dependencies.

## Example

```python
from simreality.goals import GoalBook, NPCGoal
from simreality.npc_autonomy import NPCDecisionCycle
from simreality.planning import DeterministicPlanner, PlanningAction

goals = GoalBook()
goals.add(NPCGoal("pay-rent", "tenant-7", "security", priority=8))
planner = DeterministicPlanner([
    PlanningAction("work", frozenset({"available"}), frozenset({"wages"})),
    PlanningAction("pay", frozenset({"wages"}), frozenset({"rent-paid"})),
])
cycle = NPCDecisionCycle(goals, planner)
decision = cycle.decide(
    "tenant-7", 12, {"available"}, {"pay-rent": {"rent-paid"}}
)
assert decision.actionable
assert decision.plan.actions == ("work", "pay")
```

The goal mapping is deliberately explicit so the engine does not pretend that an
abstract category such as `security` has a universally correct action sequence.
