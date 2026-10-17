# C++ Port Status

This file tracks the portable C++ core independently from Unreal Engine integration.

## Implemented on `feature/cpp-simulation-foundation`

- Shared engine-independent data contracts in `cpp/include/simreality/CoreTypes.h`.
- Simulation clock, ordered hourly/daily scheduler, runtime facade, and seeded random stream.
- Memory decay and retention floors, with time-of-day visibility based on absolute elapsed simulation hours.
- Gossip primitives: description merging, rumour retelling, corroboration, NPC-to-NPC transfer, and police-response selection.
- District pressure decisions, daily environmental dynamics, and city-scar hysteresis.
- Personal trauma accumulation, environmental tiers, and recovery.
- Legal evidence, charges, enforcement outcomes, convictions, and plea offers.
- Local reputation derived from witness memories and convictions.
- Fixer incentives, betrayal, and shared network standing.
- `SimulationWorld`, which dispatches hourly memory decay and daily district/NPC/fixer updates, records witnessed actions, and connects gossip, reputation, justice, and fixer interactions.
- Dependency-free C++ regression test executable wired into CMake/CTest.

## Current validation status

Regression tests cover clock boundaries, seeded RNG repeatability, decay floors,
day/night repeatability, rumour attribution, district/trauma thresholds, city-scar
hysteresis, evidence and plea calculations, local reputation, fixer network
propagation, and an end-to-end world step with witnessed actions, gossip, arrest
resolution, and fixer negotiation.

The Python reference suite passed: **139 tests**. The C++ test executable compiled
with C++20 and strict compiler warnings and passed. CMake/CTest could not be run in
this environment because CMake is unavailable; no Unreal Engine build has been
performed. Automated numeric differential testing across the Python and C++
implementations remains future work.

## Parity rules

- Keep the Python core as the behavioural reference while porting systems.
- Do not add Unreal headers or engine objects to the portable C++ library.
- Keep identity attribution separate from description quality: an appearance-only rumour must not silently regain a target ID.
- Corroboration must update the matching memory, not an unrelated last entry.
- Keep randomness injected and deterministic where random decisions are required.
- Keep the C++ domain model portable; no Unreal headers or objects may cross into it.
