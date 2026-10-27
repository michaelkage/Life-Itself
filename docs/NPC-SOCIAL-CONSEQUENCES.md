# Witnessed NPC Social Consequences

## Purpose

`simreality/social_consequences.py` turns a caller-described witnessed action into
persistent social consequences. One observer can update trust in the actor and
record claims they took from the event. This is the first event-to-memory bridge
for the social simulation.

## Example

```python
from simreality.social_beliefs import SocialBeliefSystem
from simreality.social_consequences import (
    ObservedClaim, SocialConsequenceRecorder, WitnessedSocialEvent,
)
from simreality.social_trust import SocialTrustLedger

trust = SocialTrustLedger()
beliefs = SocialBeliefSystem(trust)
recorder = SocialConsequenceRecorder(trust, beliefs)
result = recorder.record(WitnessedSocialEvent(
    event_id="market-incident-14",
    observer_id="shopkeeper-3",
    actor_id="resident-8",
    observed_tick=240,
    trust_direction=-1,
    trust_strength=0.6,
    claims=(ObservedClaim("resident-threatened-shopkeeper", 1, 0.9),),
))
```

## Rules and boundaries

- Trust direction/strength and each claim's direction/strength are explicit
  observer interpretations. The recorder does not assign moral meaning.
- The trust event is recorded before claims are processed. Consequently, a
  claim attributed to the actor uses the observer's updated trust as source
  reliability. This sequencing is deliberate and documented.
- Claim IDs are unique within an event and processed in sorted claim-ID order.
- Identical event replay returns the original result without applying effects
  twice. Reusing an event ID with different content raises `ValueError`.
- Generated trust-interaction and evidence IDs are namespaced by the event ID.
- This recorder models one observer's interpretation of one event. A world event
  witnessed by several NPCs should create one record per observer, allowing
  witnesses to disagree.
- The recorder doesn't yet update physical world state, execute plans, or
  automatically decide who witnessed an event; those remain explicit simulation
  responsibilities.
