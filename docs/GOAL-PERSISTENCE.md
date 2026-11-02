# NPC goal persistence

This slice adds canonical component-level persistence for the goal book and the goal-event adapter's replay index.

- `GoalBookSnapshot` preserves goal identity, owner, category, priority, timing, progress, confidence, dependencies, related entities, status, and metadata.
- `GoalEventReplaySnapshot` preserves processed event signatures so restoring an adapter does not apply the same event twice.
- Both formats are versioned and require canonical JSON.
- The replay snapshot must be restored into an adapter configured with the same goal book and policies. Policy definitions are configuration and are not embedded in this snapshot.

**Important boundary:** these snapshots are not yet fields in `SimulationWorldCheckpoint`. They provide component codecs; composite checkpoint integration and cross-validation against the authoritative event journal remain the next persistence step.
