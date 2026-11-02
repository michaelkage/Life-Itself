# NPC goal persistence

Canonical, versioned snapshots preserve both the NPC goal book and the goal-event adapter's replay index. Both are now optional components of the composite `SimulationWorldCheckpoint`.

- `GoalBookSnapshot` preserves goal identity, owner, category, priority, timing, progress, confidence, dependencies, related entities, status, and metadata.
- `GoalEventReplaySnapshot` preserves processed event signatures so restoring a world does not apply the same event to a goal twice.
- Both component formats require canonical JSON.
- The world checkpoint validates that replay history has a corresponding goal book and that every replay entry refers to an event in the authoritative world journal with an identical signature.
- Policy definitions are configuration, not saved simulation state. A restored replay snapshot must be applied to a `GoalEventAdapter` configured with the restored goal book and the same policies.

## Capture

Pass the goal book and, when event-driven goal updates are enabled, its adapter:

```python
checkpoint = SimulationWorldCheckpoint.capture(
    current_tick,
    coordinator,
    npcs,
    goal_book=goal_book,
    goal_event_adapter=goal_event_adapter,
)
payload = checkpoint.to_json()
```

A goal book may be saved without an event adapter. An adapter cannot be saved without its matching goal book.

## Restore

```python
restored = SimulationWorldCheckpoint.from_json(payload).restore()
goal_book = restored.goals

if restored.goal_event_replay is not None:
    adapter = GoalEventAdapter(goal_book, configured_policies)
    restored.goal_event_replay.restore(adapter)
```

The policy configuration must remain compatible across the save boundary. The snapshot protects against duplicate event application; it does not serialize policy definitions or silently migrate changed policy semantics.

Older world checkpoints remain readable because the new goal sections are optional and the composite schema version is unchanged.
