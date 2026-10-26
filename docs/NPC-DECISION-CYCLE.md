# NPC Decision Cycle

## Purpose

`simreality/npc_autonomy.py` connects two existing engine-independent services:
`GoalBook` chooses an actionable intention, and `DeterministicPlanner` searches
for a bounded least-cost action sequence that could satisfy its desired facts.

## Decision sequence

1. Evaluate goals for the requested NPC and simulation tick.
2. Choose the highest-scoring actionable goal using the goal book's stable tie-break.
3. Look up the caller-provided desired facts for that exact goal ID.
4. Ask the planner to find a bounded plan from the supplied current world facts.
5. Return an immutable `NPCDecision` proposal with the goal, plan result, and reason.

## Important boundaries

- The cycle never executes actions or mutates world facts or goal progress.
- Goal categories and metadata are not interpreted as hidden action rules. The caller
  must explicitly map goal IDs to desired facts.
- Missing mappings, absent goals, and planning failures are represented explicitly.
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
