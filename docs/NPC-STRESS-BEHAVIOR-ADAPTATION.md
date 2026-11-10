# NPC stress-driven behavioral adaptation

Stress remains separate from emotion, identity, and personality. This module
adds a read-only projection from an NPC's current stress assessment into
individual behavioral consideration modifiers.

## Adaptation channels

- `social_engagement`: inclination to seek or avoid social contact
- `work_performance`: expected capacity or inclination for work
- `sleep_priority`: relative importance assigned to rest
- `risk_tolerance`: willingness to accept uncertain outcomes
- `routine_flexibility`: openness to changing an established routine
- `conflict_sensitivity`: sensitivity to interpersonal tension

These are named decision inputs, not direct commands. For example, a negative
social-engagement modifier does not force an NPC to stay home; the social
decision system may weigh it alongside obligations, relationships, goals,
resources, and context.

## Individual differences

Each `StressAdaptationProfile` is owner-specific and supplies separate signed
coefficients for general stress and normalized exhaustion. The same stress
level can therefore increase work focus for one NPC, reduce performance for
another, or increase the priority of sleep for a third.

For each channel:

`modifier = clamp(stress * stress_sensitivity + exhaustion * exhaustion_sensitivity, -1, 1)`

The stress assessment comes from `NPCStressLedger.assess` and the NPC's
`CopingProfile`. This adapter is deterministic and read-only. It does not
change stress, execute routines, alter personality, or choose actions.

Profiles are authored simulation configuration and should be supplied by the
world setup after loading. No new checkpoint section is required because the
output is recomputed from persisted stress and authored profiles.

Tests: `tests/test_stress_behavior_adaptation.py`.
