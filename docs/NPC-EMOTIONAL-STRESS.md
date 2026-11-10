# NPC stress, coping, exhaustion, and recovery

Stress is tracked independently from emotional intensity, personality, identity,
and outward expression. A character may feel anger without being highly stressed,
or remain outwardly calm while stress accumulates.

## Explicit coping responses

Each `CopingProfile` belongs to one NPC and defines authored effectiveness for
reappraisal, distraction, support-seeking, and suppression, alongside resilience,
passive recovery, exhaustion threshold, and breaking point.

A stressor has an explicit intensity in [0, 1]. The selected coping strategy
reduces that load by its authored effectiveness. Suppression can also add a
delayed-load term through `suppression_cost`; it may appear effective immediately
while increasing longer-term strain. This is a simple deterministic model, not
a clinical model of human psychology.

## Accumulation and recovery

Repeated stressors accumulate up to 1. Recovery occurs only when the caller
advances the ledger with that NPC's coping profile. Each NPC has an independent
recovery clock: advancing one owner never consumes elapsed recovery time for
another owner whose profile was omitted. Recovery is
`recovery_per_tick * (1 + resilience)` per owner-specific elapsed tick, bounded
at zero. Missing profiles do not silently recover.

## Exhaustion and breaking point

`assess` reports normalized exhaustion between the configured exhaustion
threshold and breaking point, plus boolean threshold indicators. These are
signals for higher-level behavior policies. The ledger never forces a breakdown,
aggression, withdrawal, or any other action.

## Persistence and replay

`NPCStressSnapshot` schema v2 stores canonical stress state, each owner's last
recovery tick, and append-only stressor records. Schema v1 snapshots remain
readable; because v1 did not store per-owner clocks, restored owners begin at
the legacy snapshot's global tick. Reusing a record ID with identical content is idempotent; conflicting
reuse is rejected. The same world event may stress multiple NPCs, but each
event ID is unique per owner in this ledger.

Tests: `tests/test_emotional_stress.py`.
