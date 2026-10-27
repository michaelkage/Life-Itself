# World Event → NPC Memory

## Purpose

`WorldEventMemoryAdapter` converts an authoritative event into a separate
`NPCMemory` entry for one recorded witness. It uses the event's tick and explicit
attributes; it does not infer visibility, culpability, or what a witness could
actually see.

## Required event attributes

- `action_tag`: a valid `ActionTag` value from `simreality.model`.
- `target_entity_id`: the entity the memory is about.
- `memory_impact`: optional value in [0, 1], default 1.0.

Optional description attributes include `height_m`, `height_uncertainty_m`,
`jacket_colour`, `masked`, and `masked_confidence`. Missing description data
uses conservative defaults. Events with missing or unknown action/target data
produce no memory rather than inventing information.

## Determinism

- Only IDs in the event's explicit witness list can receive memories.
- Event tick converts to `timestamp_hour` using configured `ticks_per_hour`.
- The same event/witness pair is materialized once per adapter instance.
- `snapshot()` exposes stable processed-key records for save integration.
- The event journal remains unchanged; each NPC receives their own memory record.

## Boundary

This adapter is the event-to-memory bridge, not a perception simulation. A future
visibility system must decide who can witness an event and what attributes are
actually observable before writing the event record. Memory decay and rumour
transmission remain separate systems.
