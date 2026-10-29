# Persistent NPC Routines — First Implementation Slice

**Status:** Python reference implementation committed; not yet wired into the world tick, NPC save envelope, or C++ runtime.

## Design contract

A routine is an intention, not a teleport command. `RoutineBlock` says what an NPC planned to do, where, and during which part of a day. It does not prove they arrived or that the destination is available. The resolver returns a separate `RoutineResolution` describing intended and actual activity/location, outcome, delay, and the disruption records considered.

The module is engine-independent and does not read wall-clock time or global random state. Uncertain outcomes use an explicit `outcome_sample` supplied by the caller's seeded simulation stream. Reusing the same block, minute, disruptions, and sample yields the same result. Disruptions are processed in stable ID order.

## First-class disruptions

`RoutineDisruption` can represent traffic, weather, alarm/phone failure, low motivation, unexpected events, illness, location avoidance, or a social obligation. A disruption can cause a delay, redirect an NPC to a fallback activity/location, or cause the planned activity to be missed. The caller supplies severity and timing; the module does not fabricate weather, traffic, phone state, or emergencies.

Examples:
- A dead phone battery means an alarm does not ring; the NPC wakes late and may call work, arrive late, or miss the shift.
- Bad traffic makes an NPC late. A sufficiently long delay can cause a missed appointment or a fallback.
- A storm can change a work shift into work-from-home if the NPC/job scenario supports it.
- After an assault or accident at a street, an NPC's retained memory can be translated into a location-avoidance disruption. Avoidance is a personal response, not a global road closure.
- A low-motivation day can cause a delay or fallback without making every NPC unreliable.

## Uncertainty and fairness

The outcome is not encoded as a public percentage forecast. The caller draws a sample from the simulation's deterministic random stream; the resolver compares that sample to each relevant disruption's severity. A stable seed makes a replay identical, while different seeds can produce different histories. No option is guaranteed by the routine alone. Scenario rules should still preserve ordinary baseline functionality: a shop may usually have stock, but stock is state and may run out; a business can open late if its owner is delayed.

This first slice is intentionally modest. It does not yet simulate routes, calculate traffic from vehicles, derive disruption probability from a phone's battery, generate schedules for every citizen, or execute movement. Those require world state and an integrated scheduler.

## API sketch

```python
from simreality.routines import RoutineBook, RoutineBlock

book = RoutineBook([
    RoutineBlock("shift-12", "npc-12", "work", "bakery", 8 * 60, 16 * 60)
])
block = book.for_period("npc-12", 9 * 60)[0]
resolution = book.resolve(block, 9 * 60, disruptions, outcome_sample=seeded_sample)
```

## Regression coverage

`tests/test_routines.py` covers non-guaranteed attendance, alarm/phone failure, traffic, weather, low motivation, location avoidance, stable replay under reordered inputs, overlap validation, and NPC-independent routines.
