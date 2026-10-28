# Simulation Tick Replay Persistence

`SimulationTickReplaySnapshot` preserves the coordinator's completed tick request signatures and the references needed to reconstruct cached `SimulationTickResult` values.

## Restore order

1. Restore the authoritative `WorldEventLedger`.
2. Restore NPC state, including current memories, with `NPCCollectionSnapshot`.
3. Restore the world-event memory adapter's processed-key index with `WorldEventMemoryReplaySnapshot`.
4. Restore trust and observer-specific beliefs using `SocialTrustSnapshot` and `SocialBeliefSnapshot`.
5. Restore the conversation adapter's cached results with `SocialConversationReplaySnapshot`.
6. Create a fresh `SimulationTickCoordinator` wired to those restored objects.
7. Restore `SimulationTickReplaySnapshot` last.

The tick snapshot references the already-restored memory and conversation outputs instead of duplicating their full state. If a referenced event, witness memory, or conversation result is missing or inconsistent, restoration fails rather than silently repairing the save.

## Scope and limitations

This codec stores coordinator replay history and reconstructs its cached outputs. It does not itself save NPC state, trust, beliefs, event history, or the subordinate adapter indexes; those are separate versioned snapshots. Restore the same adapter configuration (including memory adapter `ticks_per_hour`) used by the original simulation.

The snapshot does not persist arbitrary external state or make unscheduled world activity autonomous. The caller remains responsible for capturing a mutually consistent set of snapshots and restoring them in the documented order.
