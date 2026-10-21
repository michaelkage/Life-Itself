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
- C++ interfaces cover life state, conditions/treatments, recovery ranges, obligations, death/ghost transitions, time-windowed ghost decisions based on NPC memories and relationships, and support resolution after death. Ghost windows restrict action types to authored `sign`, `sound`, and `dream` actions; each manifestation has a distinct persisted memory/event tag and creates a resolved, witnessed social event. `sound` can raise stress, `dream` can ease isolation/social need, and `sign` can strengthen the NPC's relationship with the ghost. When NPCs talk, they can pass these memories onward; a listener interprets a newly heard manifestation with a bounded social response, while the saved memory prevents that response from being repeatedly applied on later tellings. `CampaignCoordinator` exposes the player-facing influence call and draws its decision sample from the world's saved random stream.
- CMake includes the new source. C++ regression coverage checks recovery ranges, life/ghost transitions, and window gating; Python tests cover treatment/work effects, support/trust, estate handling, and personality-aware ghost influence.

## C++ campaign and archive integration

- `CampaignCoordinator` owns the active `SimulationWorld`, tracks the current life, records death, and allows the dead world to continue running while NPCs settle obligations.
- Starting another life snapshots the old world as an immutable archive, marks the prior character `Archived`, and creates a separate day-zero world. Archive inspection returns a detached world copy, so inspection cannot mutate the preserved snapshot.
- Versioned campaign save/load stores the active world and archive snapshots together. World format v7 persists permitted ghost actions while remaining able to read legacy v5/v6 snapshots.
- Recovery sampling uses stable FNV-1a condition IDs rather than implementation-defined `std::hash`, avoiding compiler-library-dependent outcomes.

## Determinism regression coverage

The C++ regression compares continuous simulation with save/resume at hour 8.5 and at multiple checkpoints across three additional days. Ghost actions are validated against each window's permitted action list; accepted influence updates a manifestation-specific memory, creates a persisted event linked to its witness, and applies action-specific social effects. The replay regression also checks that ghost stories propagate through NPC conversations and a newly informed listener reacts only once to the same manifestation. The campaign API consumes the saved world random stream so decisions, event counts, memory changes, emotional effects, obligations, and serialized bytes match after each checkpoint. Ghost manifestation memories use absolute world hours (not just the time of day), so their decay remains correct on later days. Coverage also checks out-of-window actions, estate/supporter debt settlement, NPC balances, life status, archive immutability, and a new life in a fresh day-zero world. The C++ core remains engine-independent; Unreal UI/animation/game-thread code is not yet wired to this API.

CI for this branch is the verification authority; report only the checks that have actually completed successfully.
