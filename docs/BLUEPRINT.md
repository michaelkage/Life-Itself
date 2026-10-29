# Life Itself — Technical Blueprint

**Life Itself** is the game/product; **Simulated Reality Engine (SRE)** is the engine and technical code name. This document defines the engine architecture. The Python under `simreality/`
is the behavioural reference; the portable C++ core is the current implementation
target. If their behavior disagrees, record the difference and resolve it against
the Python reference before changing the design.

## Status

The Python reference suite and C++/Python differential checks are run in GitHub Actions; the latest verified run should be consulted for the current count and result. The portable C++20 library and world coordinator are on `main`, with a regression executable and CMake/CTest configuration. Check current CI results for the latest status; no Unreal Engine build has been performed.

Not implemented: the Unreal worker/adapter, procedural scene assembly,
trauma-driven behaviour trees, physical custody and plea dialogue, and the
Blender-to-Unreal asset pipeline.

## Design rules

These are invariants. A port that breaks one is not a port.

1. **The simulation core touches no engine type.** No `UObject`, no
   `UWorld`, no game thread, no `FVector`. Domain modules operate on portable
   data; `SimulationWorld` is the stateful coordinator and still contains no
   engine dependencies.
2. **RNG is seeded and owned.** Domain decisions take caller-supplied samples;
   the world coordinator draws those samples from an explicit deterministic
   stream. No global or wall-clock random source is allowed.
3. **Tuning constants are named and live.** Never a literal inside a formula,
   and never a default argument bound at definition time — see bug 13 in
   MATH-NOTES, which is why the lambda parameters default to `None`.
4. **Keep domain state plain and behavior testable.** Data records stay simple;
   domain transitions remain callable without Unreal. The coordinator may own
   clock and RNG state, but it must not absorb renderer or actor behavior.

## Module map

Dependencies point one way. Nothing below the line may import anything above it.

```
                        ┌─────────────┐
   engine-dependent     │  UE5 layer  │  actors, BTs, rendering, audio, LLM
   (not yet written)    └──────┬──────┘
                               │ reads state, never mutates it
   ────────────────────────────┼────────────────────────────
   simulation core            │
   (this repo, engine-free)   ▼
   ┌──────────────────────────────────────────────────┐
   │  districts   macro inputs, DI dynamics, city scars│  1.C, 2.B
   │      │                                          │
   │      ▼                                          │
   │  ecosystem    desperation index, moral flip     │  1.C
   │      │                                          │
   │      ├──► trauma    personal stress, tiers      │  4.A
   │      │                                          │
   │  decay ──► gossip   decay, retell, morph, police │  1.A, 1.B
   │                      │                          │
   │                      ▼                          │
   │                  justice   charges, plea, law   │  2.A
   │                      │                          │
   │                      ▼                          │
   │                  fixers   reputation, betrayal  │  4.B
   └──────────────────────────────────────────────────┘
                              │
                        ┌─────┴─────┐
                        │  model    │  data contract, no logic
                        └───────────┘
```

`model.py` is the C++ header. It carries the dataclasses and the tuning
constants and nothing else.

### Module responsibilities

| Module | Brief | Owns |
|---|---|---|
| `model.py` | — | `ActionTag`, `AgeBand`, `Weather`, `TraumaLevel`, `Description`, `NPCMemory`, `NPC`, `District`, `TELEPHONE_THRESHOLD` |
| `decay.py` | 1.A | `LAMBDA_BASE`, decay constant, retention curve, `sweep`, visibility modifier |
| `gossip.py` | 1.B | `retell`, `converse`, `Rumour`, `police_response`, transmission floors |
| `ecosystem.py` | 1.C | `DI_WEIGHTS`, `desperation_index`, `evaluate`, `apply_district_pressure`, `distress_trauma` |
| `districts.py` | 1.C, 2.B | input dynamics, `ScarState`, hysteresis, `tick_day` |
| `trauma.py` | 4.A | witness/victim stress, relaxation, tier assessment |
| `justice.py` | 2.A | `Charge`, `CriminalFile`, `Stop`, `Arrest`, enforcement, plea offers |
| `reputation.py` | 4.A, 4.B | District-local accusation and conviction reputation |
| `fixers.py` | 4.B | `FixerProfile`, network standing, willingness, betrayal, `negotiate` |
| `SimulationWorld` | — | Clock dispatch, event entry points, and domain coordination |

## Engine boundary

The portable core is suitable for a worker thread, but the worker and Unreal
adapter have not been implemented. The intended boundary hands the game thread
plain snapshots.

**Game thread reads:** `NPC.trauma_level`, `NPC.personal_stress`,
`NPC.desperation_index`, `District.scar_intensity`, `ScarState`. These are the
only values the renderer and audio mixer need, and they change once per in-game
day, not per frame.

**Engine calls into the core at:** `tick_day` (daily), `converse` (on a
completed NPC-NPC interaction), `decay.sweep` (hourly, on changed memories
only), `consequence_for` (on a committed offence), `negotiate` (on a bribe
approach).

**The core never calls out.** No callbacks into the engine and no renderer
dependencies. This is the property that makes the sim testable without UE, and
it is the thing most worth preserving in the port.

## Tick model

Not per-frame. Three rates, matched to how fast each quantity actually moves.

| Rate | Work |
|---|---|
| Hourly | `decay.sweep` on each NPC's stored memories |
| On interaction | `SimulationWorld::talk` calls `gossip.converse` between co-located NPCs |
| On observed action | `record_witnessed_action` writes memories and applies witness/victim stress |
| On legal/fixer action | `resolve_offence` and `approach_fixer` use the seeded world RNG |
| Daily | District dynamics/scars → resident pressure decisions → trauma recovery → fixer-network recovery |

Nothing in the simulation is frame-rate dependent. That is deliberate: it means
the sim can be stepped faster than real time in tests and headless harnesses,
and it means a frame hitch cannot desynchronise memory decay from game time.

## Data contract → C++

`model.py` maps to the portable header `cpp/include/simreality/CoreTypes.h`.
The later Unreal adapter will translate these plain C++ types into engine-facing
objects without bringing engine dependencies into the core.

| Python | C++ |
|---|---|
| `str` | `std::string` for IDs and free text |
| `ActionTag`, `AgeBand`, `Weather`, `TraumaLevel` | portable `enum class` |
| `Description` | plain `struct Description` — **not a vector type.** See bug 5. |
| `NPCMemory`, `NPC`, `District` | plain data structs in `CoreTypes.h` |
| `list[X]` | `std::vector<X>` |
| optional result | `std::optional<X>` or `std::variant` |
| module functions | free functions in `namespace simreality` |

Two things to get right in the port that Python let slide:

- **Field order.** `Description.observations` is deliberately the last field. In
  Python a defaulted field inserted mid-list silently captures positional
  arguments — bug 14 in MATH-NOTES. In C++ aggregate initialisation this becomes
  a compile error instead, which is strictly better. Do not "tidy" the order.
- **Lazy defaults.** Every tuning constant that Python takes as `None` and
  resolves inside the function must be resolved at runtime in C++ too. Binding it
  at link time reintroduces bug 13: the tuning knob stops turning.

## UE5 integration

Four touch points, in build order.

**1. `USimSubsystem` — the bridge.** A `UGameInstanceSubsystem` owning the
simulation core and a background worker. Owns the daily/hourly tick. Exposes
read-only snapshots to the game thread. This is the only place that knows both
worlds.

**2. Behaviour trees.** `NPC.trauma_level` is currently data that nothing
consumes. Each tier maps to a behaviour tree asset:

| Tier | Tree |
|---|---|
| Baseline | default schedule, cooperative |
| Anxious | cheap locks, higher prices, avoids low-reputation actors |
| Paranoid | abandons schedule, boards windows, unlicenced firearm |
| Vigilante | joins a protection ring, refuses officers, confronts trespassers |

The sim computes the tier. The tree decides what the NPC does about it. Do not
push behaviour into the sim — that would break rule 1 for no gain.

**3. Arrest flow.** The arithmetic is done. What remains is the sequence:
consequence → custody → arrest log string → public defender → `plea_offer` →
trial. The log string and the defender's dialogue are LLM turns, grounded in the
`PleaOffer` numbers rather than improvising consequences.

**4. Rendering.** `ScarState` drives the city scars: boarded windows above 0.3
intensity, derelict facades above 0.6, police posture on `active`. These are
material blends and audio sub-mixes, all driven off one scalar per district.

## Asset pipeline

Not started — Blender is not installed. The specification is fixed by the brief
(brief 3) and needs nothing decided:

- Units in metres, +Z up, **origin at the base of the mesh**, not the pivot.
  Origin placement is the single most common cause of floating or sunk props.
- Apply all transforms on export.
- Triplanar materials so a tiling concrete blends across differently-scaled
  meshes without per-mesh UV work.
- Scale ratio locked 1:1 with the engine's `1uu = 1cm`. Decide once, before the
  first asset, or every prop needs rescaling.

## Current next steps

1. Add automated Python/C++ differential tests for numeric edge cases and seeded
   scenario traces.
2. Add a deterministic command/event journal so a complete run can be replayed;
   versioned world snapshots now preserve state and RNG continuation.
3. Integrate `simreality/routines.py` into persistent NPC/world state, derive disruptions from traffic, weather, phone/alarms, obligations and witnessed incidents, then add explicit social/spatial scheduling and autonomous world-event generation;
   the current coordinator advances systems but does not simulate pedestrian
   movement or behavior-tree schedules.
4. Build the Unreal adapter and validate worker lifecycle, snapshot handoff, and
   game-thread safety in an Unreal project.
5. Add rendering, custody/dialogue flow, and the Blender asset pipeline only
   after the portable core is measured and stable.

## Open questions

Unresolved, and each is a decision rather than a bug:

- **Routine resolution is a first Python slice, not yet integrated.** `simreality/routines.py` can resolve explicit routine blocks against explicit disruptions, but it does not yet generate schedules for all NPCs or connect movement, traffic, businesses, memory, and world ticks. Daily behavior and trauma tiers are computed,
  but no pedestrian movement, routine schedule, or behavior tree consumes them.
- **No event replay log yet.** Versioned snapshots preserve the world and RNG
  state, but the engine does not yet record commands/events to reproduce an
  entire run from its beginning.
- **Python/C++ differential testing is not automated.** Both suites pass, but a
  seeded input corpus still needs to run through both implementations and compare
  outputs.
- **LLM dialogue is unspecified.** Arrest logs and plea negotiation are the two
  places it belongs, both grounded in real numbers. Prompt design is deferred
  until the flow it interrupts actually runs.