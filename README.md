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
| `simreality/routines.py` | Persistent NPC routines | Time-windowed routines resolved against explicit disruptions; intended plans can be delayed, redirected, or missed with deterministic replay inputs |\n| `simreality/routine_tick.py` | Routine tick adapter | Selects active routines for an explicit tick, scopes supplied disruptions per NPC, and records replay-safe executions using explicit samples; called by the coordinator's named routine phase |
| `simreality/npc_autonomy.py` | NPC autonomy | Read-only decision cycle that connects selected goals to explicit desired facts and bounded plans |
| `simreality/appraisal.py` | NPC values and bias | Transparent value-weighted choice appraisal; different NPCs can rank the same hard choice differently |
| `simreality/beliefs.py` | NPC beliefs | Deterministic confidence updates from explicit supporting and contradictory evidence |
| `simreality/belief_appraisal.py` | NPC beliefs + choices | Explicitly maps claim confidence into choice impacts or bias cues, with inspectable contributions |
| `simreality/social_trust.py` | NPC relationships | Tracks observer-specific trust from deterministic interaction history; can supply a trust-based reliability input |
| `simreality/social_beliefs.py` | NPC relationships + beliefs | Uses source trust and transmitted rumour retention to update observer-specific beliefs |
| `simreality/social_decisions.py` | NPC social decision-making | Ranks choices using an NPC's own trust-weighted beliefs, values and explicit belief-effect mappings |
| `simreality/social_consequences.py` | NPC social consequences | Turns an observer's interpretation of a witnessed action into trust changes and claim evidence, with replay-safe event IDs |
| `simreality/world_events.py` | World event journal | Append-only deterministic event history with stable replay, snapshot restoration, and participant/witness queries |
| `simreality/world_event_social.py` | World event + social bridge | Validates event participants/witnesses and applies independent, explicit interpretations to NPC trust and beliefs |
| `simreality/world_event_memory.py` | World event + memory bridge | Creates deterministic witness-specific NPC memories from explicitly recorded event details |
| `simreality/memory_rumours.py` | Memory + gossip bridge | Prepares deterministic decay snapshots and rumours from each NPC's own memories; preserves attribution-loss rules |
| `simreality/social_conversations.py` | NPC conversation integration | Runs actual memory transfer and updates each listener's beliefs using their own trust in the speaker |\n| `simreality/simulation_tick.py` | Deterministic tick orchestration | Applies explicitly scheduled event memories before explicitly scheduled conversations; enforces stable order and same-tick replay rules |\n| `simreality/save_state.py` | Versioned save boundary | Canonical JSON envelope for simulation tick, authoritative world events, and scalar metadata; explicitly scopes what is not yet restored |
| `simreality/npc_save_state.py` | NPC/social persistence | Versioned canonical snapshots for NPC identity, held witness memories, and trust priors plus interaction history |
| `simreality/social_belief_save_state.py` | Belief persistence | Saves claim priors, effective evidence histories, observer-specific beliefs, and original replay inputs |
| `simreality/adapter_replay_state.py` | Adapter replay persistence | Saves processed event/witness memory keys and requires matching restored NPC memories |
| `simreality/social_replay_save_state.py` | Social adapter replay persistence | Saves conversation signatures/results and witnessed-consequence inputs/results so identical replays return recorded outcomes |
| `simreality/tick_replay_save_state.py` | Simulation tick replay persistence | Saves completed tick request history and cached-result references; restore requires the world, NPCs, memory adapter, and conversation adapter to be restored first |
| `simreality/world_checkpoint.py` | Composite world checkpoint | Combines event, NPC, trust, belief, memory, conversation and tick replay snapshots, plus optional witnessed-consequence replay, campaign lifecycle, and misconduct history in one canonical JSON checkpoint |\n| `simreality/misconduct_save_state.py` | Accountability persistence | Saves reports and append-only review decisions canonically; validates incident references against the authoritative world-event ledger on restore |

The authoritative world event journal is documented in [docs/WORLD-EVENT-LEDGER.md](docs/WORLD-EVENT-LEDGER.md); it is deliberately separate from observer-specific beliefs and consequences. The per-witness social integration is described in [docs/WORLD-EVENT-SOCIAL-INTEGRATION.md](docs/WORLD-EVENT-SOCIAL-INTEGRATION.md), and the event-to-memory bridge in [docs/WORLD-EVENT-MEMORY.md](docs/WORLD-EVENT-MEMORY.md).

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


NPC choice appraisal is documented in [docs/NPC-CHOICE-APPRAISAL.md](docs/NPC-CHOICE-APPRAISAL.md). It scores caller-supplied impacts and bias cues against an individual NPC's value profile, reports per-axis contributions, and avoids a universal good/bad label. Regression tests are in `tests/test_appraisal.py`.


The [NPC Belief Ledger](docs/NPC-BELIEF-LEDGER.md) records evidence provenance and reproducible confidence updates. It is a transparent heuristic, not a claim to determine objective truth.


Belief-aware choice appraisal is documented in [docs/NPC-BELIEF-AWARE-APPRAISAL.md](docs/NPC-BELIEF-AWARE-APPRAISAL.md) with regression coverage in `tests/test_belief_appraisal.py`. Claim-to-impact mappings remain explicit inputs; the system does not infer objective truth or silently assign moral labels.


Observer-specific trust is documented in [docs/NPC-SOCIAL-TRUST.md](docs/NPC-SOCIAL-TRUST.md), with regression tests in `tests/test_social_trust.py`. Trust remains distinct from objective truth and global reputation.


Trust-aware belief integration is documented in [docs/NPC-SOCIAL-BELIEFS.md](docs/NPC-SOCIAL-BELIEFS.md), with regression coverage in `tests/test_social_beliefs.py`. Trust is sampled when an NPC hears a report; later trust changes do not silently rewrite past beliefs.

The [social belief-aware decision adapter](docs/NPC-SOCIAL-DECISIONS.md) connects observer-specific beliefs to choice ranking, preserving each NPC's individual value profile and keeping claim-to-effect mappings explicit. See `tests/test_social_decisions.py` for regression coverage.

The [witnessed social consequence recorder](docs/NPC-SOCIAL-CONSEQUENCES.md) begins the next loop: a witnessed action can change the observer's trust in its actor and update explicit claims from that event. Identical event replay is idempotent; different observers can interpret the same world event differently. See `tests/test_social_consequences.py`.


The [memory-to-rumour adapter](docs/MEMORY-TO-RUMOUR-ADAPTER.md) calculates decay from original memory impact and event time, then reuses the existing rumour transmission rules. It is read-only: only memories already held by that NPC can become rumours, and actual transfer still requires the existing conversation system. Regression coverage is in `tests/test_memory_rumours.py`.


The [social conversation adapter](docs/NPC-SOCIAL-CONVERSATIONS.md) connects real gossip transfer to observer-specific belief updates. Conversation IDs make replay idempotent, and appearance-only rumours remain unattributed. Tests are in `tests/test_social_conversations.py`.
\n\nThe [simulation tick coordinator](docs/SIMULATION-TICK-COORDINATOR.md) now provides a small, deterministic scheduling boundary: explicitly selected event memories are materialized before explicitly selected conversations at the same tick. It does not invent visibility, proximity, or NPC schedules. See `tests/test_simulation_tick.py`.\n

The [versioned simulation save envelope](docs/SIMULATION-SAVE-STATE.md) persists the authoritative event timeline and current tick as canonical JSON. It is the first save boundary, not yet a full restore of all NPC and adapter internals; see `tests/test_save_state.py`.


NPC model persistence is documented in [docs/NPC-STATE-SNAPSHOT.md](docs/NPC-STATE-SNAPSHOT.md). It restores current NPC fields and held memories, and restores trust by replaying the saved relationship interactions; evidence histories and adapter replay indexes remain separate.


Belief history persistence is documented in [docs/BELIEF-HISTORY-PERSISTENCE.md](docs/BELIEF-HISTORY-PERSISTENCE.md), including sampled trust reliability and the remaining adapter-restoration boundaries.


The coordinator replay codec is documented in [docs/TICK-REPLAY-PERSISTENCE.md](docs/TICK-REPLAY-PERSISTENCE.md). It restores cached tick results only after the referenced adapter state is restored; it is not a single-file full-world checkpoint.


The composite [world checkpoint](docs/WORLD-CHECKPOINT.md) joins the event journal, NPC state, social trust and beliefs, adapter replay indexes, and coordinator replay history into one canonical JSON boundary. An optional witnessed-consequence recorder and `LifeItselfCampaign` lifecycle can also be captured and restored; campaign snapshots preserve death/spectator/ghost state and archived timelines. Integration and corruption tests are in `tests/test_world_checkpoint.py`. Capture is not yet a cross-component atomic operation.


The first [persistent NPC routine slice](docs/NPC-ROUTINES.md) treats routines as intentions, not guaranteed presence. Traffic, weather, failed alarms, low motivation, unexpected events, illness, social obligations, and remembered-location avoidance can alter a planned activity. Routine definitions now persist through `RoutineBookSnapshot` and an optional `routines` section in the composite checkpoint. Routine executions now have a standalone tick adapter that selects active schedules and records replay-safe results from explicit disruptions and samples. It is not yet wired automatically into the main world tick coordinator; route simulation and C++ runtime integration remain pending.


Routine outcomes can also be evaluated by [explicit routine consequence policies](docs/NPC-ROUTINES.md): configured activity/location rules can emit late-arrival or missed-appointment events without assuming a universal punishment. These consequences remain world events and are idempotent on replay; a full workplace or appointment-provider simulation is still future work.


The [misconduct reporting system](docs/MISCONDUCT-REPORTING.md) records allegations of discrimination, racial discrimination, corruption, abuse of authority, bribery, favouritism, and neglect of duty with evidence references and an append-only review history. Filing is not a verdict; review outcomes distinguish substantiated, not substantiated, and insufficient evidence. Reports and review history can now be included in the composite checkpoint, and every cited incident must exist in the authoritative event journal. An in-game UI and a separate evidence registry are not implemented.


The [routine institution ledger](docs/NPC-ROUTINES.md) accumulates explicit workplace lateness and missed-appointment events into per-person, per-institution records, with replay-safe event handling. It is not yet included in world checkpoints or connected to employment termination, wages, or appointment scheduling.


Institutional routine records can now be included in `SimulationWorldCheckpoint` via `routine_institutions=...`; restored worlds expose `RestoredSimulation.routine_institutions`, including replay-protection signatures.
