# Belief History Persistence

`BeliefLedgerSnapshot` stores explicit claim-confidence priors and every effective `Evidence` record. Restoring rebuilds confidence in canonical `(observed_tick, evidence_id)` order instead of saving only the final confidence number.

`SocialBeliefSnapshot` preserves each observer's separate ledger and the original evidence inputs used for replay validation. It also preserves the effective evidence reliability sampled from the trust ledger at the time the observation occurred. A later trust change therefore does not rewrite past beliefs after loading.

## Example

```python
from simreality import (
    SocialBeliefSnapshot, SocialBeliefSystem, SocialTrustLedger,
)

trust = SocialTrustLedger()
beliefs = SocialBeliefSystem(trust)
payload = SocialBeliefSnapshot.capture(beliefs).to_json()
restored_beliefs = SocialBeliefSnapshot.from_json(payload).restore(trust)
```

Restore the matching trust ledger first, then pass it to `SocialBeliefSnapshot.restore`. The belief snapshot retains historical sampled reliability even if current trust has since changed.

## Boundaries

These codecs preserve claim priors, evidence, per-observer belief separation, and evidence-ID replay protection. `WorldEventMemoryReplaySnapshot` now separately preserves the event-memory adapter's processed keys, provided the corresponding NPC memories are restored first. Social conversation IDs/results, social consequence recorder IDs/results, and simulation coordinator replay history are still not persisted, so this is not yet a full save that guarantees every adapter resumes without duplicate side effects.
