# Memory-to-Rumour Adapter

`MemoryRumourAdapter` connects the existing memory-decay equation to the
existing gossip `Rumour` model without creating a second rumour system.

## Contract

- Input is one NPC and that NPC's own `NPC.memories`; the authoritative world
  event journal is never queried.
- `prepare(npc, current_hour, weather)` computes decayed copies with
  `decay.sweep`, then passes each copy through the existing `gossip.retell`.
- The adapter is read-only. It returns a `MemoryRumourSnapshot` containing the
  witness ID, simulation hour, decayed memory copies, and transmissible rumours.
- `retell` remains responsible for transmission floors and attribution loss.
  When retention drops below the telephone threshold, the target ID is not
  restored or guessed; sufficiently weak memories may become unattributed
  appearance-only rumours, and the faintest are omitted.
- Repeated calls use original memory impact and timestamp, not the previous
  snapshot, so the same time always yields the same retention. No wall clock,
  randomness, or hidden elapsed-interval accumulator is used.
- This adapter does not perform a conversation or mutate the NPC. Use the
  existing `converse(listener, speaker, district_id)` API for actual transfer.

## Example

```python
from simreality import MemoryRumourAdapter, Weather

prepared = MemoryRumourAdapter().prepare(witness, current_hour=12.0, weather=Weather.CLEAR)
for rumour in prepared.rumours:
    print(rumour.action_tag, rumour.target_entity_id, rumour.retention)
```

Tests: `tests/test_memory_rumours.py`.
