# SRE-Fluid — GPU Compute Foundation

SRE-Fluid is an optional data-oriented compute subsystem for Life Itself. It
accelerates independent numerical work over large NPC populations without
moving authoritative world state, event ordering, persistence, or social graph
semantics into a GPU kernel.

## First compute pass (v0.1)

The initial pass evaluates one work item per active agent: normalized district
desperation using the existing 1.2 / 1.5 / 0.8 / 1.1 weights; personal and
environmental trauma tiers using the existing thresholds; rumour transmission
eligibility using existing attributed/unattributed retention floors; and
whether target attribution survives the existing 0.6 threshold.

This is not yet full rumour mutation or social-network propagation. Description
merging, corroboration, participant-specific belief updates, event provenance
and graph-edge traversal remain authoritative CPU work until a deterministic
GPU design for those dependencies is implemented and differentially tested.

## Buffer contract

Each agent occupies 48 bytes: three vec4<f32> values.

| Vector | x | y | z | w |
| --- | --- | --- | --- | --- |
| Identity | world x | world y | moral shackle | personal stress |
| District | overpopulation | supply shortage | weather severity | local corruption |
| Rumour | retention | speaker fidelity | description uncertainty | target known (0 or 1) |

Output is one 16-byte vec4<f32>: desperation index, trauma tier, rumour
transmittable flag, and attribution-survives flag. Dispatch ceil(agent_count / 256)
workgroups. The shader bounds-checks against the storage buffer length.

The Python CPU reference and packer are in simreality/fluid.py. The corresponding
WebGPU WGSL kernel is shaders/sre_fluid_agent.wgsl. The portable C++20 contract
is exposed by cpp/include/simreality/Fluid.h and implemented in cpp/src/Fluid.cpp;
it provides the same immutable input snapshot, explicit little-endian f32 packing,
and CPU reference evaluation. The C++ source is part of simreality_core, so the
Unreal-facing layer can build and test the data contract without a GPU SDK.

The C++ `unpack_outputs` helper decodes the shader's 16-byte result records
(four little-endian f32 values), restores stable agent IDs from the matching
input snapshot, and rejects malformed lengths, non-finite/out-of-range scores,
non-integral trauma tiers, and non-boolean flags.

## C++ backend boundary

The C++ core now exposes a device-independent `ComputeBackend` interface and
`evaluate_with_fallback` dispatcher. A future WebGPU/Vulkan adapter owns its
device buffers and reports availability and maximum batch capacity. The
dispatcher keeps small batches on the CPU, validates the immutable inputs,
checks output count/order/ranges and compares every score to the CPU reference
within a configurable absolute tolerance. Trauma tiers and rumour decisions must
match exactly. It falls back to the CPU reference if the
device is unavailable, the adapter throws (including device loss), or its
results violate the contract. A fake backend in the C++ tests exercises these
paths; it is not a real GPU implementation.

This boundary deliberately does not add a graphics API dependency to the
portable core. A production adapter still needs persistent device buffers,
asynchronous readback, capability negotiation, shader compilation, and
CPU/GPU differential tests on actual hardware.

## Determinism and integration boundary

- Stable NPC IDs stay in a CPU-side index table; GPU indices are transient.
- Inputs are immutable snapshots for one simulation phase. Outputs are proposals
  consumed at a defined tick boundary; kernels never mutate authoritative state.
- f32 buffers favour bandwidth. Differential comparisons need explicit tolerances;
  cross-vendor floating point must not be assumed bit-identical.
- Keep a CPU fallback for unsupported devices, device loss, allocation pressure,
  and small batches.
- Daily stress decay and memory decay must receive explicit simulation-time inputs;
  never advance daily simulation state once per render frame.

## Performance target and measurement

The ambition is 500,000 active agents at 60 simulation updates per second, not a
measured result. Input traffic is 24 MB per full population batch and output
traffic is 8 MB, before staging, readback, neighbour data, or rendering. Re-upload
and synchronous readback every frame may dominate kernel time. Production should
keep buffers resident, batch readback, and profile end-to-end tick latency on
named hardware.

## Next stages

1. WebGPU host runner with capability checks, persistent buffers, async readback,
   CPU/GPU differential tests and device-loss fallback.
2. Compact social-edge buffers and a gather-oriented rumour pass with deterministic
   conflict resolution.
3. Trauma accumulation and memory-decay kernels driven by explicit simulation time.
4. C++20 snapshot packing and CPU reference are now in the core; next add a backend interface for Unreal immutable snapshots.
5. Benchmarks with realistic density, edge counts, buffer reuse and full tick budgets.
