# NPC emotional state in world checkpoints

`SimulationWorldCheckpoint.capture(..., emotions=ledger)` now includes the
event-driven emotional ledger in the composite save. Restored simulations expose
it as `RestoredSimulation.emotions`.

The checkpoint validates the emotional component against the authoritative
world-event journal:

- Every saved emotional state belongs to an NPC in the checkpoint roster.
- Every emotional source event exists in the journal and matches it exactly.
- Every applied event/rule replay entry points to an existing journal event.
- The affected NPC must be a participant or witness of that source event.
- No emotional event or sampled state may be later than the checkpoint clock.

The optional `emotions` section preserves backwards compatibility with older
checkpoint JSON. If absent, `RestoredSimulation.emotions` is `None`.

The emotional event and decay rules are configuration, not saved state. After
restoration, reattach the same authored rules before processing future events.
This keeps event facts and replay history durable without silently changing
game-design policy during a save/load cycle.

Tests: `tests/test_world_checkpoint.py` and
`tests/test_emotional_events_save_state.py`.
