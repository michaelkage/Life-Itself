# Runtime clocks and host-thread transport

## Dual-clock runtime

`SimulationRuntime::advance` remains the deterministic simulation-time-only
entry point. Engine hosts that drive the simulation from rendered frames should
use `advance_frame(elapsed_real_seconds, simulation_hours_per_real_second)`.

The frame entry point tracks monotonic accumulated host time separately from
simulation hours. A rate of zero pauses simulation progression without pausing
the host clock; positive rates scale simulation hours per real second. Invalid,
negative, non-finite, and overflowing inputs are rejected. The simulation
scheduler receives only actual positive simulation-time deltas, so pause frames
produce no simulation ticks.

`SimulationWorld::advance_frame` is the integrated world entry point: it
dispatches the scheduled simulation ticks through the existing hourly and daily
world update logic. The legacy `advance(elapsed_hours)` remains supported for
deterministic tests, offline simulation, and callers that already own a
simulation-time delta.

## Lock-free command and snapshot transport

`simreality/SpscRingBuffer.h` provides a bounded, allocation-free
single-producer/single-consumer ring buffer for trivially-copyable payloads.
`SimulationCommandBus<T, N>` and `SimulationSnapshotBus<T, N>` are aliases over
the same implementation.

- Capacity must be a power of two and at least two physical slots.
- One slot is reserved to distinguish full from empty; usable capacity is
  `N - 1`.
- Producer publishes writes with release ordering; consumer observes them with
  acquire ordering. The consumer publishes slot reuse with release ordering.
- Index atomics are required to be always lock-free on the target platform.
- The type is deliberately SPSC: multiple producers or consumers must use
  external serialization or separate queues. It is not an MPMC queue.
- Payloads are copied by value; large snapshots should be represented by compact
  handles/IDs to immutable storage rather than copied into the queue.

The bus is transport only. It does not mutate authoritative world state,
perform rendering, allocate memory, or impose an engine-specific thread model.

## Verification

The dependency-free C++ core tests cover pause/resume clock behavior, invalid
rates/deltas, world-level frame advancement, queue ordering, empty/full
conditions, and the advertised usable capacity.

```bash
cmake -S cpp -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --parallel 2
ctest --test-dir build --output-on-failure
```
