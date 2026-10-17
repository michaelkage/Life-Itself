# Architecture and Development Roadmap

Status labels:
- **Verified repository content** means files currently present on the repository's default branch.
- **Proposed** means architecture or work planned in this document.
- **Not yet verified** means a claim still requires a build, test run, or in-engine check.

## Repository audit (verified from the current feature branch)

The Python reference core lives under `simreality/`, with a data contract in
`simreality/model.py`, a blueprint in `docs/BLUEPRINT.md`, math corrections in
`docs/MATH-NOTES.md`, and a unittest suite under `tests/`. The current reference
suite contains 139 tests and can be run with:

```bash
python -m unittest discover -s tests -t .
```

The Python core covers memory decay, rumour/gossip propagation, district pressure and city-scar dynamics, trauma tiers, legal evidence/plea calculations, and fixer reputation/betrayal logic. The inspected blueprint explicitly requires the core to avoid Unreal types, inject randomness rather than drawing it globally, keep tuning values named, and separate data records from behaviour.

The C++ core is being ported on `feature/cpp-simulation-foundation`. Unreal
presentation, physical custody, behavior trees, rendering/material assembly, and
the Blender-to-Unreal asset pipeline remain outside the portable library.

## Proposed target architecture

Keep a portable simulation library separate from the Unreal adapter.

- **Core data contract:** stable identifiers, plain data records, explicit units, validated ranges.
- **Simulation clock and scheduler:** fixed simulation time, hourly and daily work, interaction-triggered work; never frame-rate dependent.
- **Determinism:** explicit seed and injected random stream; stable event ordering; replayable command/event logs.
- **Domain systems:** memory/decay, gossip, environment/economy, trauma, justice, reputation/fixers.
- **World coordinator:** owns state and invokes domain systems in documented order.
- **Persistence:** versioned save schema, migrations, stable entity IDs, periodic snapshots plus event history.
- **Unreal adapter:** copies immutable snapshots to the game thread; never exposes UObjects to the simulation worker.
- **Observability:** structured logs, counters, invariant checks, seeded scenario tests, profiling hooks.

## Dependency direction

```text
Unreal presentation / actors / UI
             |
        adapter snapshots
             v
world coordinator -> domain systems
             |             |
             v             v
     scheduler/clock   plain data model
             |
       persistence + diagnostics
```

Domain systems must not call Unreal, access wall-clock time, use global random state, or mutate presentation objects.

## C++ implementation on feature/cpp-simulation-foundation

The `cpp/` directory is a portable C++20 library. It now contains the shared
data model, deterministic clock/scheduler/RNG, decay and gossip, environment and
district dynamics, trauma, justice, reputation, fixer networks, and a
`SimulationWorld` coordinator. The coordinator dispatches hourly memory sweeps
and daily district/NPC/fixer updates, and exposes event-driven witness,
conversation, enforcement, and fixer interactions. Versioned snapshots preserve
world state, simulation time, fixer networks, and RNG continuation. The CMake
target builds the library and dependency-free regression executable.

The Python reference suite and the C++ regression executable have both passed in
the current work environment. CMake itself was unavailable, so the C++ target
was compiled directly with the available C++20 compiler. Automated numerical
differential tests across implementations and Unreal-specific validation remain.

## Roadmap and exit criteria

### Phase 0 — Baseline and contracts
1. Run the existing Python unittest command on a clean checkout.
2. Record exact test count, Python version, branch/commit, and baseline result.
3. Document units, ID rules, legal ranges, update cadence, and save compatibility.
**Exit:** baseline is reproducible and model contract is documented.

### Phase 1 — Portable C++ foundation
1. Build the C++20 library and smoke tests with MSVC and one secondary compiler where available.
2. Port model fields and enums with explicit Python-to-C++ mappings.
3. Add validation and parity tests for the data contract and clock boundaries.
4. Add a seeded RNG interface and stable event ordering.
**Exit:** clean build; deterministic tests pass; no Unreal dependency in core.

### Phase 2 — Port domain systems
Port one module at a time in dependency order: decay, gossip, ecosystem, districts, trauma, justice, fixers, reputation. Preserve Python as the reference implementation until differential tests agree across edge cases and parameter sweeps.
**Exit:** each C++ module has equivalent seeded tests and numerical tolerances documented.

### Phase 3 — World coordinator and persistence
The world-step API, hourly/daily dispatch, and versioned save/load are implemented.
Remaining: format migrations, event journaling, and replayable command records.
**Exit:** a seeded scenario produces identical state hashes across repeated runs and save/load continuation; recorded events can replay from a known snapshot.

### Phase 4 — Unreal integration
Create an Unreal adapter that owns the worker lifecycle, queues commands, and publishes immutable snapshots. Keep UObject access on the game thread. Add cancellation and clean shutdown before enabling background simulation.
**Exit:** a small test map can pause, advance, inspect, save, and reload the simulation without race conditions.

### Phase 5 — First playable neighborhood
Build one compact district with a small population, daily schedules, social contact, memory propagation, a basic local economy, and visible persistent environmental changes.
**Exit:** a 30-minute test session creates measurable changes that survive save/load and can be explained through logs.

### Phase 6 — Scale and content pipeline
Add simulation levels of detail, spatial/social indexing, profiling budgets, Blender export conventions, wear masks, procedural materials, and streaming integration.
**Exit:** performance targets are measured on target hardware before population or city size is expanded.

## Tooling note

Unreal Engine and Visual Studio are not required to design the architecture or write portable C++ files. They are required later to validate Unreal-specific code, build the actual game target, and test rendering/physics/animation integration. Until then, use Python tests and a standalone C++ compiler when available; label all uncompiled Unreal code clearly.
