# SIMULATED-REALITY-ENGINE

A seamless, asynchronous open-world simulation: dynamic NPC memory decay, mutating
rumour networks, macro-environmental desperation modelling, and zero-cut state
transitions.

**Status: simulation core only.** No engine yet — see [Where this is going](#where-this-is-going).

## Running it

```
python -m unittest discover -s tests -t .
```

33 tests, no dependencies beyond the standard library. Python 3.10+ (needs `X | Y`
type syntax).

## What's here

Three sub-engines, deliberately free of any engine dependency:

| Module | Brief section | What it does |
| --- | --- | --- |
| `simreality/decay.py` | 1.A Memory Decay | Exponential decay with situational modifiers |
| `simreality/gossip.py` | 1.B Gossip Network | Rumour mutation through social contact |
| `simreality/ecosystem.py` | 1.C Desperation Matrix | Environmental pressure and behavioural status flips |
| `simreality/model.py` | 4.A Trauma Levels | Shared data records, all engine-independent |

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

## Six bugs in the original design

The brief's equations do not do what the prose around them says they do. All six
are fixed here, with derivations in [docs/MATH-NOTES.md](docs/MATH-NOTES.md):

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

## Where this is going

The simulation core is the part of this project that is interesting and the part
that needs no renderer. It is written to run on a background thread behind
Unreal's render loop, which is what the brief asks for and what makes it testable
without an engine. Nothing in it may touch a UObject or a game thread.

Not yet built, all of it engine-dependent:

- **Arrest and legal loop** (brief 2.A) — physical custody chain, Chaos Vehicles,
  World Partition streaming, LLM-driven plea negotiation
- **Procedural scene assembly and city scars** (brief 2.B) — Material Parameter
  Collections driven by district desperation
- **Trauma-driven NPC schedules** (brief 4.A) — the tiers exist as data; the
  behaviour trees that consume them do not
- **Fixer network** (brief 4.B) — reputation and betrayal logic
- **Blender → Unreal pipeline** (brief 3) — zero-point pivots, vertex-colour wear
  masks

### Constraints to resolve before installing the engine

- **Disk.** This needs a separate drive. Unreal 5 alone is 100+ GB, before Visual
  Studio, before a single world partition cell.
- **Build order.** Install the C++ toolchain *first* and port `model.py` while it
  is still fresh — the data contract is the thing that has to survive translation,
  and it is much cheaper to port before the behaviour code lands on top of it.