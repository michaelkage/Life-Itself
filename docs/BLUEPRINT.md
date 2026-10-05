# Blueprint

Architecture for the SIMULATED REALITY ENGINE. Authoritative for the C++ port
and the UE5 integration. The Python under `simreality/` is the executable
version of this document — if the two disagree, the Python is right and this
document is stale.

## Status

Every system in the brief that can be specified without the engine is built,
tested, and calibrated. 100 tests. Nothing below the engine boundary is waiting
on UE5, Blender, or a C++ toolchain.

Not built, and genuinely blocked on the engine: procedural scene assembly,
trauma-driven behaviour trees, the arrest *flow*, the Blender→Unreal pipeline.

## Design rules

These are invariants. A port that breaks one is not a port.

1. **The simulation core touches no engine type.** No `UObject`, no
   `UWorld`, no game thread, no `FVector`. Everything in `simreality/` is plain
   data and plain functions over it.
2. **RNG is injected, never drawn.** Every function that is stochastic takes an
   `rng` sample from the caller. No module calls `random`. This is what makes
   the whole simulation deterministic and reproducible from a seed.
3. **Tuning constants are named and live.** Never a literal inside a formula,
   and never a default argument bound at definition time — see bug 13 in
   MATH-NOTES, which is why the lambda parameters default to `None`.
4. **Structs, not classes with behaviour.** Plain data with `frozen` where
   appropriate. Behaviour lives in module functions. This maps to C++ structs and
   free functions with no translation cost.

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
| `fixers.py` | 4.B | `FixerProfile`, willingness, betrayal, `negotiate` |

## Engine boundary

The core runs on a worker thread and hands the game thread plain snapshots.

**Game thread reads:** `NPC.trauma_level`, `NPC.personal_stress`,
`NPC.desperation_index`, `District.scar_intensity`, `ScarState`. These are the
only values the renderer and audio mixer need, and they change once per in-game
day, not per frame.

**Engine calls into the core at:** `tick_day` (daily), `converse` (on a
completed NPC-NPC interaction), `decay.sweep` (hourly, on changed memories
only), `consequence_for` (on a committed offence), `negotiate` (on a bribe
approach).

**The core never calls out.** No callbacks into the engine, no event bus. This is
the property that makes the sim testable without UE, and it is the thing most
worth preserving in the port.

## Tick model

Not per-frame. Three rates, matched to how fast each quantity actually moves.

| Rate | Work |
|---|---|
| Hourly | `decay.sweep` on active memories; recompute `VisibilityModifier` |
| On interaction | `gossip.converse` between two NPCs |
| Daily | `districts.tick_day` → `ecosystem.apply_district_pressure` → `trauma.daily_update` per resident → behaviour tree re-evaluation |

Nothing in the simulation is frame-rate dependent. That is deliberate: it means
the sim can be stepped faster than real time in tests and headless harnesses,
and it means a frame hitch cannot desynchronise memory decay from game time.

## Data contract → C++

`model.py` maps to a single header. Field names carry the brief's names so the
comparison is mechanical.

| Python | C++ |
|---|---|
| `str` | `FName` for entity ids, `FString` for free text |
| `ActionTag`, `AgeBand`, `Weather`, `TraumaLevel` | `enum class : uint8` |
| `Description` | `struct FDescription` — **plain data, not `FVector`.** See bug 5. |
| `NPCMemory` | `struct FNPCMemory`, brief's field names retained |
| `NPC` | `USTRUCT`, not `UCLASS`. No methods on the hot data. |
| `District` | `USTRUCT` |
| `list[X]` | `TArray<X>` |
| `float \| None = None` | `TOptional<float>` or a sentinel resolved inside |
| module functions | free functions in `namespace SimReality` |

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

## Order of work on the new machine

Disk first. UE5 needs 100+ GB and C: does not have it.

1. **Install a C++ toolchain.** Visual Studio with the Desktop C++ workload.
   Nothing can be ported before this.
2. **Port `model.py`.** One header, no logic. Get it compiling and add a static
   assert per `ActionTag`/`AgeBand`/`TraumaLevel` so an enum mismatch is a
   compile error rather than a wrong number at runtime.
3. **Port leaf modules, no dependencies:** `decay` → `gossip` → `ecosystem`.
   Port the test file alongside each. A module without tests is a module that
   was not ported, it was rewritten.
4. **Port `districts`, `trauma`, `justice`, `fixers`.** Same rule.
5. **Verify against Python.** Run both on the same seeded inputs and diff. The
   Python is the reference; C++ must match it or justify the difference in this
   document.
6. **Install UE5**, then the four integration points above, in order.
7. **Blender**, last, once the world layout is fixed. Asset scale is expensive
   to change after the city is built.

## Open questions

Unresolved, and each is a decision rather than a bug:

- **Trauma tiers are consumed by nothing.** The tiers exist as data; the
  behaviour trees that would read them do not. Until they exist, the simulation
  has no visible effect on play, only on the legal and reputation layers.
- **Reputation has no source.** `fixers.willingness_to_deal` reads
  `REPUTATION_FLOOR = 0.35`, and `CriminalFile.reputation` defaults to 0.5.
  Nothing writes reputation, so every player is permanently just above the floor.
  This is the one gap that will look like a bug in play rather than an absence.
- **The fixer network is not a network.** `FixerProfile` is a list of
  independent actors. Standing does not propagate between fixers, so "the
  network" has no collective behaviour yet. `known_betrayers` is the only
  cross-actor state.
- **LLM dialogue is unspecified.** Arrest logs and plea negotiation are the two
  places it belongs, both grounded in real numbers. Prompt design is deferred
  until the flow it interrupts actually runs.