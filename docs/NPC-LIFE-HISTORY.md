# NPC autobiographical life history

`NPCLifeHistory` stores observer-owned memories of authoritative world events. A memory retains the event ID and tick as objective provenance while its interpretation, emotional impact, identity impact, and linked psychological records remain explicitly subjective. Two NPCs can therefore retain different accounts of the same event without rewriting the event journal.

## Recording and retrieval

Create an `AutobiographicalMemory` with a unique memory ID, owner, source event, tick, involved NPC IDs, and the owner's interpretation. Optional conflict and psychological-learning decision IDs preserve links to prior systems. A turning-point flag and tags are authored inputs; the module does not infer what should become important.

`recall_salience(memory_id, current_tick, half_life_ticks=...)` returns a retrieval weight. Ordinary memory salience decays exponentially; a marked turning point retains full salience. Neither calculation deletes, edits, nor forgets the underlying record. A future retrieval policy can combine this signal with context, but this module does not decide what an NPC recalls spontaneously.

## Forgiveness and reconciliation

`act(..., action="forgive")` records a deliberate forgiveness choice. `action="reconcile"` is a separate later choice and requires prior forgiveness for the same owner, target, and event. Neither action erases the memory, changes the historical event, restores trust, or forces renewed contact. Trust remains in the social relationship systems and must be changed by their own explicit evidence and policies.

## Persistence and boundaries

`LifeHistorySnapshot` is canonical, versioned JSON. Memory/action IDs are replay-safe; reusing an ID with different content fails. Histories are append-only and observer-scoped. Source-event and NPC-roster cross-validation is performed by the composite world checkpoint when this component is included. This is a reference-system component; it does not yet implement automatic memory formation, spontaneous recall, dialogue, or engine-side storage.
