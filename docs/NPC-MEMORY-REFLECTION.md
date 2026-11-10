# NPC Memory Reflection

MemoryReflectionLedger records a person's later reinterpretation of an existing autobiographical memory without modifying the original memory or its source world event.

Each MemoryReinterpretation identifies the owner, memory, tick, previous interpretation, new interpretation, and rationale. The ledger verifies that the memory belongs to the owner, that reflection does not predate the memory, and that the supplied previous interpretation matches the current end of that memory's reflection chain. Entries are append-only and replay-safe.

The original AutobiographicalMemory remains unchanged. current_interpretation returns the latest reflection when one exists, otherwise the original interpretation. This allows dialogue and decision systems to explicitly choose whether to consult the original account or the owner's current understanding.

MemoryReflectionSnapshot provides a canonical, versioned component-level JSON codec. It is integrated into SimulationWorldCheckpoint through `memory_reflections=...` and restored as `RestoredSimulation.memory_reflections`. Capture requires the reflection ledger to share the exact `NPCLifeHistory` instance being checkpointed. Every reflection owner and tick is checked against the saved NPC roster and checkpoint clock; a checkpoint containing reflections without the matching life history is rejected. Older checkpoints without a `memory_reflections` section remain valid.

The ledger does not infer why an NPC changed their mind, alter identity or trust, forgive another person, or force a behavior. Those outcomes require separate explicit systems.

Tests: tests/test_npc_memory_reflection.py.
