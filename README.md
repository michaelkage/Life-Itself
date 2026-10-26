# Life Itself

**Life Itself** is the game and product. **Simulated Reality Engine (SRE)** is its technical engine name: a persistent, systemic open-world life simulation where people remember, forget, talk, react, build reputations, experience trauma, navigate justice, and make deals. The long-term ambition is a grounded, reactive open world with the freedom and systemic depth of a real-life crime sandbox, while keeping everyday life—not just crime—at the centre.

The engine is designed for continuous simulation: dynamic NPC memory decay, mutating rumour networks, district-level pressure, personal stress, local reputation, justice, fixer networks, deterministic world stepping, utility-based fallback activity selection, read-only world diagnostics, and save/load continuation.

**Development status: simulation core in progress.** The Python reference models the
engine-independent systems; the portable C++20 implementation ports them into a
standalone C++20 library and adds a world coordinator. Unreal presentation,
animation, physics, and asset integration are not implemented.

## Product and technical naming

- **Product/game:** Life Itself
- **Engine / code name:** Simulated Reality Engine (SRE)
- **Python package and C++ namespace:** `simreality` (kept stable for code compatibility)
- **Repository:** currently `SIMULATED-REALITY-ENGINE`; the README and product-facing documentation use the Life Itself brand.

## Running it

```
python -m unittest discover -s tests -t .
```

The Python reference suite uses only the standard library and is run by GitHub Actions. Python 3.10+ is required (the code uses `X | Y` type syntax).

For the portable C++ core:

```
cmake -S cpp -B build
cmake --build build
ctest --test-dir build --output-on-failure
```

C++20 and CMake 3.20+ are required.

## What's here

Engine-independent Python reference systems:

| Module | Brief section | What it does |
| --- | --- | --- |
| `simreality/model.py` | — | Shared data records and tuning constants. The C++ port contract |
| `simreality/decay.py` | 1.A Memory Decay | Exponential decay with situational modifiers |
| `simreality/gossip.py` | 1.B Gossip Network | Rumour mutation through social contact |
| `simreality/ecosystem.py` | 1.C Desperation Matrix | Environmental pressure and behavioural status flips |
| `simreality/districts.py` | 1.C, 2.B City Scars | Macro dynamics over time, scar hysteresis |
| `simreality/trauma.py` | 4.A Trauma Levels | Personal stress accumulation, behavioural tiers |
| `simreality/justice.py` | 2.A Legal | Evidence, charges, plea bargaining |
| `simreality/fixers.py` | 4.B Fixers | Fixer incentives, betrayal, network propagation |
| `simreality/reputation.py` | 4.A, 4.B | Local reputation from witness memories and convictions |
| `simreality/goals.py` | NPC autonomy | Deterministic goal tracking, prerequisite checks, deadline urgency, and stable priority selection |
| `simreality/planning.py` | NPC autonomy | Bounded symbolic action planning with preconditions, effects, costs, and deterministic tie-breaking |

`simreality/model.py` is the contract for the existing C++ domain port — it holds records and
constants only, no behaviour. The new NPC goal and planning modules are currently Python-only; their implementation boundaries and regression coverage are documented in [docs/NPC-GOALS-IMPLEMENTATION.md](docs/NPC-GOALS-IMPLEMENTATION.md) and [docs/NPC-PLANNING-IMPLEMENTATION.md](docs/NPC-PLANNING-IMPLEMENTATION.md).

The C++ library under `cpp/` now includes the portable data model, deterministic
clock/scheduler/RNG, memory decay, gossip, environmental pressure and district
scars, trauma, legal evidence and plea calculations, local reputation, fixer
networks, and a `SimulationWorld` coordinator for hourly/daily updates and
event-driven conversations, witness memories, arrests, fixer approaches, and
versioned world snapshots that preserve simulation time and RNG state.

### A rumour, end to end

The mechanic the whole design hangs on, running as a test:

```
Crime committed → witness memory → told to a friend → 3 more hops →
description drifts → name lost → police stop the wrong person
```

At 2 in-game hours per hop, the target's ID survives about 3 hops, then the
rumour degrades to an appearance and travels roughly 10 more. A patrol receiving it
acts on `stop and search matching tall-ish, black jacket, masked` — for someone
who only ever saw a silhouette, or was wearing a coat they did not choose to wear.

That same rumour, when it reaches police as an *actionable* memory, does build a
charge. `tests/test_integration.py` runs both paths end to end.

## Model corrections

The brief's equations and prose do not always do what they say. The first fourteen
issues below are documented with derivations and measured numbers in
[docs/MATH-NOTES.md](docs/MATH-NOTES.md).

In the original design:

1. **λ can go negative** — the Trauma modifier is subtracted, so a petty-theft
   memory *strengthens* with age instead of fading.
2. **Permanent memories are impossible** — any λ > 0 reaches zero; armed assault
   was "forgotten" after about a year. Now decays toward a permanent floor.
3. **DI and MoralShackle were on different scales** — DI ranged 0–4.6 against a
   shackle of 0.2–0.95, so moderate pressure criminalised the whole city on day
   one and both ends of the shackle range were indistinguishable.
4. **The telephone effect was inert** — at the specified rate, retention never
   fell below the transmission threshold, so rumours stayed precise accusations
   forever and never morphed.
5. **`DescriptionDelta` as a `FVector` cannot hold a rumour** — merging witnesses
   needs per-trait uncertainty; a point value makes corroboration *widen*
   uncertainty instead of sharpening it.
6. **Age compounds across hops** — an emergent consequence, not a decision: crimes
   witnessed by elderly citizens travel far enough to go effectively unreported.
7. **One witnessed armed assault made a vigilante** — brief 4.A's tiers mix
   personal and environmental causes in the same row, so a linear impact-to-tier
   mapping reached "zero law presence" off a single crime.
8. **The city was frozen** — brief 1.C gives DI a daily cycle but no dynamics for
   any input, so nothing could ever change and the city-scar trigger in 2.B could
   never fire.
9. **City scars flickered** — a strict `>` test with no hysteresis strobed the
   entire city between clean and ruined on alternate days.
10. **Arrests outran their evidence** — a rumour that has lost its subject can
    produce a stop but the brief's loop treated that as an arrest, so charges
    accumulated against a predicate fact naming nobody.
11. **Corruption collapsed the legal system** — as a multiplier, a corrupt
    district left a 0.01% chance of any arrest, so the city stopped having one.
12. **Fixer betrayal was strictly dominant** — keeping the bribe, clearing your
    warrants, and removing the witness costs nothing, so a rational fixer betrays
    100% of the time and "might betray" was a guaranteed ambush.

Found while building:

13. **The tuning knob was welded shut** — `lambda_base` defaulted to the module
    constant, which Python binds at definition time, so rebinding it at runtime
    did nothing.
14. **A reordered field silently captured the wrong argument** — a mid-list
    defaulted dataclass field bound a colour dict to `observations`, with no
    error raised.
15. **Reputation had no source** — a stored default never changed and memory-only
    reputation disappeared as evidence decayed. Local reputation now derives from
    actionable accusations and durable conviction records.
16. **Connected fixers never betrayed** — exposure outweighed betrayal incentives
    across the useful range. The exposure weight now modulates rather than blocks
    betrayal.
17. **Fixer standing did not propagate** — networks now share standing changes,
    recover gradually, and have a pressure-dependent trust ceiling.
18. **Burned fixers can become more likely to squeal** — this is a feedback
    consequence of the incentive model, not an implementation defect; regression
    tests preserve it intentionally.

## Where this is going

The simulation core is the part of this project that is interesting and the part
that needs no renderer. It is written to run on a background thread behind
Unreal's render loop, which is what the brief asks for and what makes it testable
without an engine. Nothing in it may touch a UObject or a game thread.

Not yet built, all of it engine-dependent:

- **Arrest and legal loop** (brief 2.A) — the arithmetic is done; what remains is
  physical custody, Chaos Vehicles, World Partition streaming, and the LLM-driven
  plea dialogue that `PleaOffer` grounds
- **Procedural scene assembly** (brief 2.B) — `ScarState` is built and exposes
  `boarded_windows`, `derelict_facades`, and police posture; the Material
  Parameter Collections that consume it do not exist
- **Trauma-driven NPC schedules** (brief 4.A) — the tiers exist as data; the
  behaviour trees that consume them do not
- **Unreal adapter** — the C++ core is portable, but no Unreal worker lifecycle,
  command queue, or immutable game-thread snapshots have been implemented
- **Blender → Unreal pipeline** (brief 3) — zero-point pivots, vertex-colour wear
  masks

### Constraints to resolve before installing the engine

- **Disk.** This needs a separate drive. Unreal 5 alone is 100+ GB, before Visual
  Studio, before a single world partition cell.
- **Build order.** Keep the C++ core portable and continue porting one system at a
  time with regression tests against Python. Install Unreal only when the portable
  systems and hardware/storage plan are ready; Python remains the behavioral
  reference until differential parity is established.

### Decision-making and world diagnostics

Unscheduled NPC hours now use a deterministic utility-based activity selector. It
considers time of day, employment, transport reliability, stress, social need,
isolation, available shops, service capacity and trusted local contacts. Explicit
schedule entries still take precedence. The selected activity includes a score
and human-readable reason for debugging and future tooling.

The portable diagnostics module provides read-only world metrics (housing,
employment, resident and business cash, stock, unresolved events and average
wellbeing proxies) plus invariant checks for duplicate IDs, broken district/home
references, housing capacity, numeric ranges and business inventory. These tools
are intended for regression tests, scenario telemetry and a future Unreal adapter;
they do not mutate authoritative world state.

Daily work hours and commute disruption are reset after the daily payroll and
resident update, preventing yesterday's attendance from being counted again on
subsequent days.
