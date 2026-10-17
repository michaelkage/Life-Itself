# Development Timeline

These are planning ranges, not promises. Assumption: one developer learning as they go, using AI assistance, working part-time (roughly 8–15 focused hours per week), with existing Python core retained as the reference. Hardware, familiarity with C++, Unreal, and scope can move these estimates substantially.

| Phase | Estimated effort | Target outcome | Dependency |
|---|---:|---|---|
| 0. Baseline and repo audit | 2–5 days | Re-run Python tests, map modules, record known issues and contract | Python 3.10+ |
| 1. Portable C++ foundation | 1–3 weeks | Compile core types, clock, seeded RNG, scheduler, smoke tests | C++20 compiler; CMake recommended |
| 2. Port domain modules | 4–8 weeks | C++ parity for decay, gossip, ecosystem, districts, trauma, justice, fixers, reputation | Phase 1 and differential tests |
| 3. Coordinator and persistence | 3–6 weeks | Repeatable world stepping, save/load, schema versioning, replay diagnostics | Phases 1–2 |
| 4. Unreal setup and adapter | 2–5 weeks | Build a minimal Unreal project and safely connect simulation snapshots | Supported PC, disk space, Unreal and C++ toolchain |
| 5. First playable neighborhood | 6–12 weeks | One small district, a limited population, schedules, social propagation, visible changes | Phase 4 |
| 6. Content pipeline and scale | 2–6+ months | Blender pipeline, environment variation, profiling, simulation LOD, streaming | Measured vertical slice |

A credible first playable neighborhood is likely a **several-month project**, not a weekend build. A polished, large-scale persistent city is a much longer undertaking and should not be promised until performance is measured on the target machine.

## Recommended scope gates

1. **Do not port every feature at once.** Port one Python module, add parity tests, then move to the next.
2. **Do not add LLM decisions to the critical simulation loop yet.** Start with deterministic rules; later use language models for bounded dialogue or interpretation, with validated structured outputs and a deterministic fallback.
3. **Do not optimize a hypothetical city.** Profile a small neighborhood first and use measurements to decide simulation LOD.
4. **Do not treat AI-generated code as verified.** Every system needs a build, tests, and a defined failure mode before it is called complete.
5. **Install the heavy game tools only when the portable core and hardware/storage plan are ready.** Until then, Python and a standalone C++ compiler can move the project forward.

## Current implementation status

- Repository default branch: Python simulation core exists, as described in the architecture roadmap.
- Feature branch `feature/cpp-simulation-foundation`: initial C++20 data contract, clock, deterministic random stream, hourly/daily scheduler, runtime facade, CMake build definition, smoke tests, and planning documents have been added.
- A prior version of the initial clock and smoke-test source was compiled locally, but the **latest expanded branch has not been built or tested as a complete checkout**. A fresh Git clone was attempted in the current environment but outbound GitHub access was unavailable.
- Still required: run CMake/CTest against the current branch, run the existing Python suite, complete field-by-field model parity, and test on the intended Windows machine before merging.
