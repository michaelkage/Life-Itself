# Adapter Replay Persistence

`WorldEventMemoryReplaySnapshot` saves the processed `(event_id, witness_id)` index for the world-event-to-NPC-memory adapter. The actual NPC memories remain owned by `NPCCollectionSnapshot`; this codec records the exact memory associated with each processed key.

## Restore order

1. Restore the authoritative `WorldEventLedger`.
2. Restore NPCs and their current memories with `NPCCollectionSnapshot`.
3. Create a fresh `WorldEventMemoryAdapter` using the restored event ledger and the same `ticks_per_hour` configuration.
4. Restore the replay index with `WorldEventMemoryReplaySnapshot.from_json(payload).restore(adapter, npcs)`.

Restore rejects missing witness NPCs, missing saved memories, unknown events, non-witness relationships, duplicate keys, and non-empty destination indexes. It does not attach memories itself: a mismatch is treated as an inconsistent save rather than silently repaired.

## Scope

This is one adapter's replay index, not a complete simulation save. It does not yet persist conversation replay results, social consequence recorder results, or `SimulationTickCoordinator` request history. Those still need their own codecs before a whole-world save can promise replay-safe continuation across every adapter.
