# NPC Memory Recall

NPCMemoryRecallAdapter retrieves an NPC's existing autobiographical memories when explicitly observed cues match that NPC's authored MemoryRecallProfile.

## Authored associations

Each MemoryRecallRule links one cue ID to a memory tag, an involved NPC ID, or both. A rule can specify bounded sensitivity. A profile also sets an emotional-weight coefficient; emotional impact is not assigned universal psychological meaning by the engine.

## Retrieval

The recall method receives current cue exposures, tick, memory half-life, minimum score, and top-K limit. A memory is eligible only when at least one observed cue has a matching authored rule and all selectors on that rule match. Its score is the strongest matching cue contribution multiplied by memory salience and the profile's explicit emotional factor. Turning-point salience follows the existing life-history policy.

Results include the original immutable memory and matched cue/rule provenance. Ordering is deterministic: score descending, then memory tick descending, then memory ID. Recall is owner-scoped and read-only. It does not create memories, alter interpretations, initiate dialogue, or force behavior.

## Boundaries

- No rule means no cue-triggered recall.
- A cue cannot retrieve another NPC's memories.
- top_k bounds retrieval; minimum_score supports selective access.
- The adapter does not infer that similar words, places, or people are psychologically equivalent. The simulation supplies canonical cue IDs and explicit associations.

Tests: tests/test_npc_memory_recall.py.
