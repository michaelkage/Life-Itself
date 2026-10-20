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

## C++ campaign and archive integration

- `CampaignCoordinator` owns the active `SimulationWorld`, tracks the current life, records death, and allows the dead world to continue running while NPCs settle obligations.
- Starting another life snapshots the old world as an immutable archive, marks the prior character `Archived`, and creates a separate day-zero world. Archive inspection returns a detached world copy, so inspection cannot mutate the preserved snapshot.
- Versioned campaign save/load stores the active world and archive snapshots together. World lifecycle persistence remains versioned separately (world format v6 reads legacy v5 snapshots).
- Recovery sampling uses stable FNV-1a condition IDs rather than implementation-defined `std::hash`, avoiding compiler-library-dependent outcomes.

## Determinism regression coverage

The C++ regression compares a continuous campaign with a campaign saved at hour 8.5 and resumed through the first post-death day. It checks ghost influence inside and outside its time window, estate/supporter debt settlement, NPC balances, life status, byte-identical campaign snapshots, archive immutability semantics, and a new life in a fresh day-zero world. The C++ core remains engine-independent; Unreal UI/animation/game-thread code is not yet wired to this API.

CI for this branch is the verification authority; report only the checks that have actually completed successfully.
