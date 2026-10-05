# SIMULATED-REALITY-ENGINE

A seamless, asynchronous open-world simulation: dynamic NPC memory decay, mutating
rumour networks, macro-environmental desperation modelling, and zero-cut state
transitions.

**Status: simulation core complete.** Every system in the brief that can be built
without the engine is built and tested. See [docs/BLUEPRINT.md](docs/BLUEPRINT.md)
for the architecture and [Where this is going](#where-this-is-going) for what
remains.

## Running it

```
python -m unittest discover -s tests -t .
```

100 tests, no dependencies beyond the standard library. Python 3.10+ (needs `X | Y`
type syntax).

## What's here

Seven sub-engines, deliberately free of any engine dependency:

| Module | Brief section | What it does |
| --- | --- | --- |
| `simreality/model.py` | — | Shared data records and tuning constants. The C++ port contract |
| `simreality/decay.py` | 1.A Memory Decay | Exponential decay with situational modifiers |
| `simreality/gossip.py` | 1.B Gossip Network | Rumour mutation through social contact |
| `simreality/ecosystem.py` | 1.C Desperation Matrix | Environmental pressure and behavioural status flips |
| `simreality/districts.py` | 1.C, 2.B City Scars | Macro dynamics over time, scar hysteresis |
| `simreality/trauma.py` | 4.A Trauma Levels | Personal stress accumulation, behavioural tiers |
| `simreality/justice.py` | 2.A Legal | Evidence, charges, plea bargaining |
| `simreality/fixers.py` | 4.B Fixers | Reputation, willingness, betrayal |

`simreality/model.py` is the contract for the C++ port — it holds records and
constants only, no behaviour.

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

## Fourteen bugs

The brief's equations and prose do not do what they say. Six were in systems
that existed (1-6), six were in systems that had never been built (7-12), and two
were faults in this implementation (13-14). All fixed, with derivations and
measured numbers in [docs/MATH-NOTES.md](docs/MATH-NOTES.md).

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
- **Fixer network** (brief 4.B) — the logic is done; `FixerProfile` is a list of
  independent actors with no propagation of standing between them
- **Blender → Unreal pipeline** (brief 3) — zero-point pivots, vertex-colour wear
  masks
- **Reputation has no source** — `fixers` reads it and nothing writes it, so every
  player sits permanently just above the floor. The one gap that will read as a
  bug in play rather than an absence.

### Constraints to resolve before installing the engine

- **Disk.** This needs a separate drive. Unreal 5 alone is 100+ GB, before Visual
  Studio, before a single world partition cell.
- **Build order.** Install the C++ toolchain *first* and port `model.py` while it
  is still fresh — the data contract is the thing that has to survive translation,
  and it is much cheaper to port before the behaviour code lands on top of it.
  Port each module with its tests, and diff against the Python: the Python is the
  reference implementation, not a rough draft.