# Unified NPC motivational projection

The goal system can consume a temporary motivational score projection built from
three independent inputs:

- **Emotion:** an owner-specific `NPCEmotionalState` snapshot.
- **Stress:** an owner-specific `StressBehaviorSignal`, produced by the existing
  stress assessment and adaptation pipeline.
- **Experience:** optional goal adjustments produced by the strategic experience
  guidance system.

## Explicit rules

`MotivationalGoalRule` maps one goal ID to an emotion axis, a stress
consideration channel, or both. Signed coefficients describe how strongly that
signal should affect the goal's score. No axis-to-goal relationship is inferred
from names or semantic similarity.

`NPCMotivationalAdapter.assess` returns an immutable `NPCMotivationalState`
with each contribution exposed separately. Inputs must belong to the same NPC;
future-dated emotional or stress samples are rejected. Experience adjustments
must reference goals owned by that NPC.

The combined adjustment is clamped to [-0.25, 0.25] before it is passed to
`NPCDecisionCycle.decide(..., goal_motivational_adjustments=...)` or
`NPCActionReplanningCoordinator.replan(..., goal_motivational_adjustments=...)`.
The adjustment changes only the current ranking calculation. It does not mutate
goal priority, progress, confidence, status, emotion, stress, memory, identity,
or authoritative world facts.

## Boundaries

Emotion, stress, and autobiographical experience remain distinct sources.
Stress is not treated as an emotion; displayed expression is not substituted
for felt emotion; reported experience does not become personal memory. The
adapter does not generate new goals, force actions, or claim that its authored
coefficients are a universal psychological model.

Tests: `tests/test_npc_motivation.py`.
