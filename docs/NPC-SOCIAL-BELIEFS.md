# Trust-Aware NPC Beliefs

## Purpose

`simreality/social_beliefs.py` connects observer-specific social trust to the
existing deterministic belief ledger. When an NPC receives a source-attributed
report, the source's current trust score becomes the reliability used to update
that NPC's confidence in the claim. The same report can therefore affect two NPCs
differently without declaring either NPC objectively correct.

## Observation rules

- Each observer has an independent belief ledger.
- `SocialBeliefSystem.observe(observer_id, evidence)` looks up trust in
  `evidence.source_id` for that observer.
- If no observer-source relationship exists, reliability defaults to `0.5`.
- The incoming evidence's `source_reliability` is intentionally overridden by
  the trust score; evidence strength, direction, claim, source, ID, and tick are
  preserved.
- Trust is sampled when the report is observed. Later relationship changes do
  not rewrite earlier belief updates. A later report can use the new trust level.
- Evidence replay is idempotent for identical content and rejects conflicting ID
  reuse. Snapshots are sorted deterministically by observer and claim.

## Example

```python
from simreality.beliefs import Evidence
from simreality.social_beliefs import SocialBeliefSystem
from simreality.social_trust import SocialTrustLedger

trust = SocialTrustLedger({("skeptical-npc", "witness-4"): 0.2,
                           ("loyal-npc", "witness-4"): 0.9})
beliefs = SocialBeliefSystem(trust)
report = Evidence("report-17", "guard-was-bribed", "witness-4", 1, 0.8, 1.0, 120)

skeptical_view = beliefs.observe("skeptical-npc", report)
loyal_view = beliefs.observe("loyal-npc", report)
```

## Boundaries

Trust is a social relationship signal, not proof of truth. A highly trusted source
can be mistaken or deceptive, and a distrusted source can tell the truth. This
first integration uses trust as a direct reliability heuristic; future systems
may add source-specific expertise, evidence quality, context, or deliberate bias
without collapsing those concepts into one number.

The implementation is deterministic for a given event order and trust state. It
does not automatically replay all past observations when trust changes, because
that would silently rewrite an NPC's remembered interpretation of history.
