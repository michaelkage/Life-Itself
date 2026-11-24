# Deterministic lane traffic admission

`LaneTrafficCoordinator` provides deterministic, tick-driven lane capacity
reservations for pedestrian corridors, vehicle lanes, queues, and other
constrained movement channels. It is deliberately separate from geometric
collision detection: the host supplies lane identity and physical movement,
while this subsystem arbitrates admission to finite lane capacity.

## Contract

- Configure each lane with a positive slot capacity.
- Call `advance_tick` with a strictly increasing simulation tick. Reservations
  whose exclusive expiry tick has arrived are removed before new requests.
- Submit all simultaneous requests for a tick together through `resolve`.
  Arbitration is per lane and deterministic: higher authored priority first,
  then longer consecutive wait, then lexicographically smaller entity ID.
- Successful grants occupy capacity for a bounded lease. Renewing an existing
  reservation is idempotent and refreshes its priority; callers should continue
  requesting while they occupy the lane.
- Denied requests accrue wait credit, preventing stable equal-priority ordering
  from starving larger IDs indefinitely.
- `release` frees a slot immediately and clears the entity's wait history.
  Lane capacity cannot be reduced below its active reservation count.

All timing uses caller-supplied integer simulation ticks; no wall clock,
thread scheduling, random sampling, or unordered-container iteration affects
results. A lane reservation is an admission token, not proof of collision-free
geometry. The world driver remains responsible for intersection conflicts,
vehicle dimensions, braking distance, pedestrian separation, and releasing a
token on lane exit or route change.

## Build and test

```bash
cmake -S cpp -B build
cmake --build build
ctest --test-dir build --output-on-failure
```
