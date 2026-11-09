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
WebGPU WGSL kernel is shaders/sre_fluid_agent.wgsl.

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
4. C++20 snapshot packing and a backend interface for Unreal immutable snapshots.
5. Benchmarks with realistic density, edge counts, buffer reuse and full tick budgets.
