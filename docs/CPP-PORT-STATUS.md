# C++ Port Status

This file tracks the portable C++ core independently from Unreal Engine integration.

## Implemented on `feature/cpp-simulation-foundation`

- Shared engine-independent data contracts in `cpp/include/simreality/CoreTypes.h`.
- Simulation clock, ordered hourly/daily scheduler, runtime facade, and seeded random stream.
- Memory decay and retention floors, with time-of-day visibility based on absolute elapsed simulation hours.
- Gossip primitives: description merging, rumour retelling, corroboration, NPC-to-NPC transfer, and police-response selection.
- Dependency-free C++ regression test executable wired into CMake/CTest.

## Current validation status

Regression tests have been added for clock boundaries, seeded RNG repeatability, decay floors, day/night repeatability, rumour attribution thresholds, conflicting attribution, and preservation of unrelated listener memories during corroboration.

**The current branch has not yet had a complete C++ build or Python suite run in this environment.** Treat the implementation as work in progress until a clean CMake build, CTest run, and Python unittest run pass. No Unreal Engine build has been performed.

## Parity rules

- Keep the Python core as the behavioural reference while porting systems.
- Do not add Unreal headers or engine objects to the portable C++ library.
- Keep identity attribution separate from description quality: an appearance-only rumour must not silently regain a target ID.
- Corroboration must update the matching memory, not an unrelated last entry.
- Keep randomness injected and deterministic where random decisions are required.
