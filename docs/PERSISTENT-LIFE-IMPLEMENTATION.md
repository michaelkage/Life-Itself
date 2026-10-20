# Persistent Life & Legacy — Implementation Status

This document distinguishes the portable Python reference implementation from integration that is still pending.

## Implemented in the reference core

- Health conditions carry severity, recovery rate, persistence, duration and per-activity limits.
- Daily advancement applies gradual recovery.
- Social obligations can be settled once, charge available funds, and update stress and directed trust.
- Missed obligations apply stress and trust consequences.
- Campaign life states enforce active -> spectator -> ghost transitions; death records a cause and simulation day.
- Ghost influence requires an explicitly allowed window and respects a cooldown.
- Death snapshots preserve a detached copy of the world.
- A campaign manager can archive an ended timeline, start a separate day-zero world for a new life, and visit an archived timeline through a detached copy.
- Versioned JSON serialization supports save/load of the active world and archived timelines.
- Regression tests cover health recovery, obligation settlement and default consequences, death/ghost rules, world separation, archive immutability, and save/load continuation.

## Important boundaries

The current code is a deterministic, engine-independent reference layer. It does not yet simulate clinical diagnosis, uncertain prognoses, treatment availability/cost, work attendance, household care, NPC decision-making under ghost influence, or inheritance and resolution of obligations after a debtor dies. Those require explicit domain rules and connections to the existing NPC, economy, scheduler, and world coordinator rather than invented effects in the lifecycle module.

The portable C++ core and Unreal adapter are also not yet integrated with these Python lifecycle types. The next integration phase should port the same contracts to C++, connect daily health/obligation processing to the world scheduler, and add cross-language differential tests.

## Verification

The GitHub Actions workflow runs Python regression tests and Linux/Windows C++ builds on pushes to main. A commit is not treated as verified until the corresponding workflow reports success.
