# Persistent Life & Legacy — Implementation Status

This subsystem is being connected to the existing simulation, rather than treated as an isolated design document.

## Python reference systems

- Health conditions persist severity, duration, activity limitations, and gradual recovery.
- Daily life now models treatment costs/effectiveness, bounded uncertain recovery estimates, work capacity, missed wages, stress, and care hours.
- NPC support transfers money, reduces recipient stress, records care providers, and improves directed reciprocal trust.
- Obligations can be settled or missed with money/stress/trust consequences. After death, outstanding debt is considered against the estate, then possible supporters are evaluated using relationships and personality traits; unresolved amounts remain explicit.
- Ghost influence is restricted to authored time windows and allowed action types. The receiving NPC's spiritual openness, fearfulness, stubbornness, memories, and relationships determine receptivity; decisions are logged.
- Campaign life states enforce active -> spectator -> ghost transitions. Death snapshots preserve a world, and starting another life creates a separate day-zero world with read-only archived timelines.
- JSON save/load is versioned for the base world and campaign archives.

## C++ world integration

- `LifeCoordinator` is now part of the portable C++ core and is exposed through `SimulationWorld::life_system()`.
- The world coordinator invokes lifecycle processing on scheduler daily ticks. Medical recovery/treatment costs are applied, and health-adjusted work hours feed the existing wage/missed-work system rather than paying wages twice.
- C++ interfaces cover life state, conditions/treatments, recovery ranges, obligations, death/ghost transitions, time-windowed ghost decisions based on NPC memories and relationships, and support resolution after death.
- CMake includes the new source. C++ regression coverage checks recovery ranges, life/ghost transitions, and window gating; Python tests cover treatment/work effects, support/trust, estate handling, and personality-aware ghost influence.

## Known integration boundary

The C++ lifecycle coordinator is not yet encoded inside the existing binary `WorldPersistence` snapshot; lifecycle state is currently persisted by the Python campaign JSON layer. Before treating C++ saves as full-fidelity campaign saves, the lifecycle records and random/decision state must be added to that binary format with a versioned migration and round-trip tests. The C++ core is engine-independent; this does not yet wire Unreal UI/animation/game-thread code to the lifecycle API.

## Verification

The run at commit `ff2cdca4f8a7cb0c44c710e7b131ad307a976236` passed the complete Python unittest suite and Linux/Windows C++ configure, build, and CTest jobs. Lifecycle binary save/load changes were added afterward and are awaiting their own CI run; do not treat those newer changes as verified until that run succeeds.
