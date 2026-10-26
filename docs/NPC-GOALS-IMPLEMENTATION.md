# NPC Goals — First Implementation Slice

**Status:** implemented in the Python reference layer; C++ parity and world/campaign integration remain future work.

## Purpose

Daily schedules answer "where does this NPC go?" Goals answer "why are they doing it?" This module introduces persistent intentions without tying them to Unreal actors or to a particular frame rate.

## Data and behavior

- `NPCGoal` records an owner, category, base priority, progress, confidence, optional deadline, dependency IDs, related entities, and status.
- `GoalBook` validates goal records and prerequisite references, updates progress, tracks terminal outcomes, evaluates readiness, and selects the best actionable goal for an NPC.
- `GoalEvaluation` explains whether a goal is actionable and provides its deterministic score.
- `snapshot()` returns a stable immutable representation ordered by goal ID for persistence/replay comparisons.

## Selection contract

A goal is selectable only when it is active and all prerequisites are completed. A failed, abandoned, or blocked prerequisite makes the dependent goal unachievable for evaluation; the system reports this rather than silently selecting it.

The current score is:

```text
score = priority × (0.5 + 0.5 × confidence) × urgency × (1 - 0.25 × progress)
```

- Confidence changes priority but does not erase the goal.
- A deadline raises urgency as it approaches, capped at a 2× multiplier.
- Progress can move backwards when callers report lost resources or changed circumstances.
- Equal scores are resolved by lexicographically sorted goal IDs, never by container iteration order or random draws.
- No wall-clock time or global RNG is used.

The score is a starting policy, not a claim that human decisions reduce to one universal utility function. Future work should allow goal-specific constraints and personality-driven trade-offs without making NPCs perfectly rational.

## Validation and boundaries

Goal IDs must be unique; priorities, ticks, progress, and confidence must be in valid ranges; dependencies must be unique and already registered. Prerequisites are registered before dependent goals, so the graph is acyclic by construction and unknown references are rejected.

This first slice deliberately does **not** generate plans, spend resources, schedule physical actions, mutate relationships, or advance goals automatically. Those actions require world facts and should be owned by a later planning/execution layer. It also does not yet persist goals through the existing campaign save format or provide C++ parity.

## Regression coverage

`tests/test_goals.py` covers priority selection, prerequisite resolution, deadline urgency, deterministic tie-breaking, failed prerequisites, validation, rollback on rejected registration, and stable snapshots.
