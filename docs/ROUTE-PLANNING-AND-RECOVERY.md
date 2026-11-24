# Deterministic route planning and stalled-agent recovery

## Directed lane graph

`TrafficRoutePlanner` stores directed transitions between lane IDs. Every
edge declares a non-negative traversal cost, congestion cost per occupant,
and hazard penalty. An optional intersection/movement pair identifies the
right-of-way reservation required when entering the destination lane.
Geometry, lane capacity, conflict-zone definitions, and physical occupancy
remain host-authored.

`plan(source, destination, occupancy)` uses deterministic Dijkstra search.
The edge cost is:

`traversal_cost + hazard_penalty + congestion_cost_per_occupant * destination_lane_occupancy`

The caller supplies an occupancy snapshot, so route choice is repeatable for
the same graph and snapshot. Equal-cost paths use lexicographically ordered
lane sequences as a stable tie-break. Invalid/non-finite/negative costs are
rejected; an unreachable destination raises an error. The planner does not
silently invent a fallback route.

## Reservation look-ahead

After selecting a route, call `reservation_lookahead` with the current step
index and desired look-ahead depth. It emits lane requests and any associated
intersection movement requests for upcoming steps. Submit those requests to
the existing coordinators using their explicit simulation ticks. This helper
only constructs intents: it does not claim that a reservation was granted.

Keep current lane and intersection grants while acquiring look-ahead grants.
Only call `SimulationWorld::advance_npc_on_reserved_route_segment` after the
required destination grants are live. That operation retains old occupancy
through the physical movement step and releases it only after movement
succeeds.

## Stalled-agent recovery

`RouteProgressMonitor` accepts a monotonically increasing simulation tick
and a finite progress measure per entity. A strict increase resets the
stalled counter; otherwise elapsed ticks accumulate. Once the configured
threshold is reached, observations return
`RouteRecoveryAction::ReplanRequested`.

The monitor is deliberately advisory. It does not move or despawn agents,
release lane/intersection reservations, or assume that a route is blocked.
The host should inspect current traffic state, calculate an alternative using
a fresh congestion snapshot, acquire replacement look-ahead reservations,
and only then commit a route-segment handoff. If admission fails, the entity
continues to hold its existing occupancy protection.

## Build and test

```bash
cmake -S cpp -B build
cmake --build build
ctest --test-dir build --output-on-failure
```

The route-planning test covers shortest path, congestion-driven alternatives,
stable equal-cost selection, reservation intent generation, unreachable routes,
invalid edges, stalled detection, progress reset, and stale-tick rejection.
