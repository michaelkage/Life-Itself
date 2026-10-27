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

## Social trust history

```python
from simreality import SocialTrustLedger, SocialTrustSnapshot

trust = SocialTrustLedger()
payload = SocialTrustSnapshot.capture(trust).to_json()
restored_trust = SocialTrustSnapshot.from_json(payload).restore()
```

Trust snapshots preserve the initial observer-target priors and interaction records, not only the computed trust score. This allows deterministic trust to be rebuilt from the same history.

## Scope and restoration boundary

This restores the NPC model records and their current memory contents. `SocialTrustSnapshot` separately stores observer-target trust priors and the full interaction history, then rebuilds trust by canonical replay. It does not restore belief evidence history, conversation transfer indexes, memory-adapter processed keys, or simulation coordinator replay indexes. This is not yet a full live-world continuation save. Snapshots are versioned independently from `SimulationSaveEnvelope`.
