# Live traffic planning, journey leases, and deadlock recovery

## Live route costs

TrafficRoutePlanner::plan_live(source, destination, lane_coordinator) captures LaneTrafficCoordinator::occupancy_snapshot() at call time and feeds it into the deterministic route cost function. The snapshot includes active reservations only; it is a deterministic admission-pressure signal, not a geometric occupancy sensor. Hosts should call it at a serialized simulation-tick boundary and replan when meaningful traffic state changes. plan(...) remains available for explicit/replayable snapshots.

## Multi-segment journey lease renewal

JourneyReservationManager tracks the lane and optional intersection movement that an entity is physically occupying. advance_and_renew(tick, ...) advances both coordinators (thereby expiring overdue leases) and submits renewal requests for every tracked occupancy. Call it before the current lease expires. A denied renewal is an operational fault signal; it does not authorize movement or release anything.

After a route-segment handoff has physically completed and the host has verified clearance, update tracking to the new occupancy. forget_after_clearance only removes the manager's renewal responsibility. It intentionally does not release coordinator tokens; explicit release remains a separate host action after physical clearance. Never stop renewing a lane or conflict zone while an entity still occupies it.

The manager assumes one active lane and at most one active intersection movement per entity, matching the coordinator request contracts. Multi-lane look-ahead requests remain a separate admission phase.

## Deadlock detection and safe recovery

TrafficDeadlockDetector accepts a wait-for graph (waiter -> blocker) and returns deterministic, lexicographically sorted strongly connected components with at least two entities. Each component is a deadlock candidate requiring host validation against current lane/intersection ownership and physical state. Malformed/self edges and duplicates are rejected.

Detection is read-only. Recovery must preserve every current occupancy token:
1. Validate the cycle against live reservation owners and actual physical blockage.
2. Choose an authored safe action (yield, back out along a validated path, or replan).
3. Acquire any replacement lane/intersection reservations while retaining current occupancy.
4. Execute movement only through the guarded route-segment handoff.
5. Release old tokens only after the host confirms physical clearance.

No detector or recovery helper teleports entities, revokes reservations, or assumes that a cycle alone proves a safe reverse maneuver.

## Validation

simreality_traffic_recovery_tests covers live renewal of both resource types, the non-release behavior of tracking removal, cycle/no-cycle detection, stable cycle ordering, and malformed input rejection. Existing route planner tests cover congestion-based path changes and stale route intents.
