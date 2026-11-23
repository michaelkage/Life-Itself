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

## Verification

The C++ core test target covers stable radius/AABB queries, entity movement and
removal, invalid coordinates, field-of-view and occlusion behavior, acoustic
attenuation, and bounded separation force.

```bash
cmake -S cpp -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --parallel 2
ctest --test-dir build --output-on-failure
```
