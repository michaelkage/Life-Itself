# NPC emotional event persistence

The event-driven emotional ledger stores transient emotion intensities, the
simulation tick at which they were sampled, authoritative source-event facts,
and the event/rule application signatures needed to prevent duplicate impulses.

`EmotionalEventSnapshot` wraps that ledger snapshot in a canonical, versioned
JSON envelope. Capture is read-only. Restore reconstructs the ledger and
validates its internal records before returning it.

The snapshot preserves:

- Each NPC's current normalized emotion intensities.
- The ledger's current simulation tick.
- Source event IDs, ticks, event types, participants, witnesses, and attributes.
- The exact event/NPC/rule signatures already applied.

This means a restored ledger can safely receive an exact retry without applying
the same emotional impulse again. The original rule definitions are not stored:
the simulation must reattach its authored event, relationship, memory, and decay
rules when advancing after restoration.

This codec is a component-level persistence boundary. It does not yet add the
emotional ledger to the composite `SimulationWorldCheckpoint`; that integration
must also validate NPC ownership and source-event membership against the
checkpoint's authoritative event journal.

Run the regression tests with:

```bash
python -m unittest tests.test_emotional_events_save_state
```
