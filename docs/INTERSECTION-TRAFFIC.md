# Deterministic intersection conflict-zone reservations

`IntersectionTrafficCoordinator` is the right-of-way layer above lane
capacity admission. A host authors each movement as a set of conflict-zone
identifiers. The coordinator does not infer road geometry or turn paths.

## Contract

- Configure a movement with a non-empty intersection ID, movement ID, and
  non-empty set of conflict-zone IDs.
- Advance a strictly increasing integer simulation tick before resolving.
- Submit all simultaneous requests as one batch. Each entity may request one
  intersection movement per tick; malformed or unknown requests reject the
  entire batch before arbitration.
- A grant reserves the complete movement zone set atomically. Any overlap with
  an active or earlier-granted movement at that intersection blocks admission;
  disjoint movements may be granted concurrently.
- Arbitration is deterministic: higher authored priority, then greater
  consecutive wait credit, then lexicographically smaller entity ID. Wait
  credit resets when an entity stops requesting or receives a grant.
- Existing grants renew only for the same movement. A holder cannot silently
  switch movements before releasing its current reservation.
- Leases expire at their exclusive expiry tick. Explicit release frees the
  conflict zones immediately.
- All decisions use simulation ticks. No wall clock, random source, or
  unordered iteration participates.

Conflict-zone definitions are an authored abstraction. Hosts must define zones
conservatively enough to cover swept vehicle/pedestrian footprints and safety
buffers. This coordinator does not calculate braking distance, physical
occupancy, signal phases, or collision geometry. It complements rather than
replaces lane-capacity reservations and predictive collision avoidance.

## SimulationWorld enforcement

`SimulationWorld` exposes movement configuration, tick advancement, batch
resolution, and release. The
`advance_npc_on_reserved_intersection_movement` entry point refuses to advance
an NPC unless it owns the matching live intersection/movement reservation.
Hosts should release the token after the entity clears the conflict area and
should continue renewing it while occupancy persists.

## Build and test

```bash
cmake -S cpp -B build
cmake --build build
ctest --test-dir build --output-on-failure
```
