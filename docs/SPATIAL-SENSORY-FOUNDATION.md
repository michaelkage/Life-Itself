# Spatial and sensory foundation

The C++ core now provides a deterministic, engine-independent spatial broadphase
and bounded sensory calculations in `simreality/Spatial.h`.

## Spatial partition

`SpatialPartition` is a uniform 3D grid with caller-configured positive cell
size. Entity IDs and cell buckets use ordered containers, so query output is
stable regardless of insertion order. `upsert` moves an entity between cells,
`erase` removes both its position and bucket membership, and queries return
sorted IDs after exact geometric filtering.

- `query_radius(center, radius)` uses the grid to find candidate cells, then
  applies an exact Euclidean-distance check.
- `query_aabb(minimum, maximum)` returns entities inside an inclusive box.
- Non-finite coordinates, invalid ranges, out-of-range cell indices, and
  pathological queries spanning more than one million cells are rejected.

The index is a derived acceleration structure; it does not own NPC lifetime or
change the authoritative world state.

## Vision and acoustics

`assess_vision` evaluates range, a forward vector, a full field-of-view angle,
and an explicit occlusion input. It returns the distance and angular offset as
well as the visibility decision. Geometry/occluder tracing remains the caller's
responsibility.

`assess_sound` computes inverse-square received intensity with explicit source
power, range, ambient-noise threshold, and a caller-supplied occlusion
attenuation in [0, 1]. It does not invent sound propagation through buildings
or weather.

## Crowd separation

`compute_separation` calculates a deterministic local repulsion vector from
neighbors closer than a preferred distance and caps the resulting force. It is
a steering primitive, not a complete traffic-lane or pedestrian navigation
solver; lane topology, collision constraints, velocities, and right-of-way
remain world-driver inputs.

`compute_lane_following` projects an agent onto an ordered 3D lane centerline,
selects a deterministic look-ahead target measured along the polyline, computes
a desired velocity, and returns a force-limited steering correction. Degenerate
segments are skipped, fully degenerate centerlines are rejected, and ties resolve
to the earliest segment. The function is stateless: lane occupancy, collision
avoidance, traffic priority, and vehicle integration remain world-driver duties.

## Verification

The C++ tests cover stable radius/AABB queries, entity movement and removal,
invalid coordinates, field-of-view and occlusion behavior, acoustic attenuation,
bounded separation force, lane look-ahead and steering limits, world-level
NPC registration, nearby queries, facing direction, occlusion filtering,
spatially discovered witness evidence, acoustic reach/occlusion queries, and
lane-driven movement updates.

`SimulationWorld::set_npc_spatial_state` registers an existing NPC's position
and facing vector in a derived spatial index. `nearby_npcs` provides deterministic
radius queries, while `visible_npcs` first broadphases by range and then applies
each registered NPC's facing direction, field of view, and caller-supplied
occlusion set. `audible_npcs` uses the same broadphase and applies inverse-square
sound attenuation, ambient-noise thresholding, and per-NPC occlusion factors.
`record_spatially_witnessed_action` uses the actor's registered
position to discover witnesses, excludes the actor, and passes only visible,
non-occluded NPCs into the existing witnessed-action evidence pipeline. This
connects physical perception to durable NPC memories and event witness lists
without requiring callers to manually assemble witness IDs.

`advance_npc_on_lane` runs the lane-following steering primitive against an
NPC's registered position and velocity, integrates the force-limited velocity
over a host-supplied frame delta, clamps speed to the requested maximum, updates
the spatial index, and turns the NPC's facing vector toward its movement
direction. It is an explicit host-frame operation rather than an implicit
simulation-hour side effect; callers choose which NPCs to advance at each LOD.

Spatial state is deliberately not added to the durable NPC schema yet; hosts
must restore or rebuild these derived positions, facing vectors, and velocities
when loading a world.

```bash
cmake -S cpp -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --parallel 2
ctest --test-dir build --output-on-failure
```


## Predictive collision avoidance

`compute_collision_avoidance` evaluates each moving neighbor's closest
approach over a caller-supplied prediction horizon. Overlapping predicted
trajectories produce a bounded acceleration away from the closest-approach
point; exact stationary overlaps use a stable entity-ID-derived axis. Neighbor
input order is canonicalized, duplicate/self identities are rejected, and the
result reports predicted conflict count and earliest conflict time.

This is a deterministic local avoidance primitive, not a global traffic or
intersection solver. Hosts should combine it with lane reservations, right-of-way
rules, vehicle dimensions, braking envelopes, and authoritative collision
resolution. The caller owns broadphase selection and must provide all relevant
moving bodies within the prediction horizon.
