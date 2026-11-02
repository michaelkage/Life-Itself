# Goal-aware daily routines

**Status:** First deterministic bridge from long-term NPC intentions to recurring daily activity.

The goal system now influences daily routines through explicit `GoalRoutinePolicy` mappings. A policy links one goal category to one routine activity and declares the maximum priority bonus, time/resource cost, and minimum confidence required.

## How it works

`GoalLifeAdapter.assess(GoalLifeContext(...))` returns an immutable `GoalLifeAssessment`. For each matching goal and routine belonging to the same NPC, it:

1. Ranks actionable goals using the existing `GoalBook` evaluation.
2. Matches only activities explicitly configured by policy.
3. Allocates the supplied discretionary time and resource budgets in deterministic goal-priority order.
4. Calculates a life-capacity factor from stress, competing obligations, social support, and recent setbacks.
5. Proposes a bounded routine-priority increase for accepted matches.

Example: an NPC with an entrepreneurship goal may have a research activity receive higher routine priority. If that NPC has no available time or resources, the proposal is rejected rather than pretending the activity can happen.

## Example

```python
policy = GoalRoutinePolicy(
    policy_id="business-research",
    goal_category="entrepreneurship",
    routine_activity="research",
    priority_bonus=0.4,
    time_cost_minutes=30,
    resource_cost=2.0,
)

adapter = GoalLifeAdapter(goal_book, routine_book, (policy,))
assessment = adapter.assess(GoalLifeContext(
    owner_id="npc-17",
    current_tick=120,
    available_minutes=90,
    available_resources=5.0,
    stress=0.3,
    obligation_load=0.4,
    social_support=0.6,
    recent_setbacks=0.1,
))
```

## Important boundaries

This is a proposal layer, not an automatic behavior executor. It does not rewrite a routine, spend money, invent an opportunity, or advance goal progress. The simulation runtime must decide whether and how to apply a proposal. Policy mappings and daily life signals are explicit inputs, making the result deterministic and inspectable.

Stress, obligations, support, and setbacks influence capacity but do not decide whether an NPC's ambition is worthwhile. The same goal can remain important while becoming harder to pursue under pressure.

Regression coverage: `tests/test_goal_life.py`.
