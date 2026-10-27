# Versioned Simulation Save Envelope

`SimulationSaveEnvelope` serializes the simulation tick, canonical world-event journal, and optional scalar metadata as versioned JSON.

## Example

```python
from simreality import SimulationSaveEnvelope, WorldEventLedger

ledger = WorldEventLedger()
save = SimulationSaveEnvelope.capture(120, ledger, metadata={"build": "development", "seed": 42})
payload = save.to_json()
loaded = SimulationSaveEnvelope.from_json(payload)
restored_events = loaded.restore_event_ledger()
```

## Guarantees

- Schema version 1; canonical JSON output.
- Events sorted by `(tick, event_id)`.
- Rejects duplicate event IDs, events later than the save tick, duplicate metadata keys, malformed JSON, and unsupported schema versions.
- Restoring the event journal does not mutate NPC memories, beliefs, trust, or conversation outcomes.

## Scope

This is a first save boundary, not yet a complete world save. NPC memory state, observer-specific trust and beliefs, conversation replay indexes, memory-adapter processed keys, and coordinator replay history still need codecs before every live subsystem can resume exactly after restart.
