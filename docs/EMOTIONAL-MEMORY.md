# Cue-Triggered Emotional Memory

`EmotionalMemoryProfile` defines explicit associations for one NPC. Each association links an autobiographical memory ID and an observed cue ID to a named emotion axis, with a bounded sensitivity.

The world driver supplies literal cue IDs and exposure strengths. Cue IDs can represent a person being present, entering a location, hearing a sound, or encountering a situation. The adapter does not perform perception or semantic matching: an association activates only when its exact cue ID appears in the supplied observation map.

For each active association, the response strength is:

`abs(memory.emotional_impact) × cue exposure × association sensitivity × current memory salience`

Memory salience uses the existing autobiographical retrieval decay and half-life. Contributions are grouped by emotion axis and the aggregate intensity is capped at 1.0. The response retains each contributing memory, association, cue, exposure, salience, and sensitivity for inspection.

Separate axes can coexist. For example, one memory can activate resentment toward a person while another activates affection toward that same person. The engine does not collapse these into a single positive/negative relationship score or decide which feeling wins.

`EmotionalMemoryAdapter.evaluate` is deterministic and read-only. It does not mutate the life history, personality, or emotional event ledger, and it does not execute behavior. A caller may explicitly route the returned axes into emotional appraisal or a later emotion-state update.

The profile is authored configuration and is not stored in the world checkpoint. The autobiographical memories it references are persisted through `life_history`; cue observations and profile definitions must be supplied by the simulation after loading.

Tests: `tests/test_emotional_memory.py`.
