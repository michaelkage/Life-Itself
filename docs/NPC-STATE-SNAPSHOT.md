# NPC State Snapshot

`NPCStateSnapshot` and `NPCCollectionSnapshot` add a versioned JSON boundary for current NPC state.

The codec preserves:
- NPC identity, age band, moral shackle, desperation index, trauma tier, and personal stress.
- Each currently held memory, including its action tag, target attribution, retention, timestamp, physical-description uncertainty, colour weights, mask confidence, and observation count.
- Canonical JSON output and stable collection ordering by entity ID.

## Example

```python
from simreality import NPC, NPCCollectionSnapshot

citizens = [NPC("citizen-2"), NPC("citizen-1")]
payload = NPCCollectionSnapshot.capture(citizens).to_json()
restored = NPCCollectionSnapshot.from_json(payload).restore()
assert tuple(restored) == ("citizen-1", "citizen-2")
```

## Scope and restoration boundary

This restores the NPC model records and their current memory contents. It does not restore trust interactions, evidence history, conversation transfer indexes, or simulation coordinator replay indexes. Those need explicit codecs of their own; this module does not claim full live-world continuation. Snapshots are versioned independently from `SimulationSaveEnvelope`.
