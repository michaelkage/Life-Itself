# Social Belief-Aware NPC Decisions

## Purpose

`simreality/social_decisions.py` completes a small vertical slice from social
information to choice ranking. It reads one NPC's current beliefs from
`SocialBeliefSystem`, copies their confidence values into a temporary ledger,
and passes them to `BeliefAwareAppraiser` alongside the NPC's own values,
bias weights, candidate choices, and explicit claim-to-effect mappings.

## Example

```python
from simreality.appraisal import ChoiceOption, NPCValueProfile
from simreality.beliefs import Evidence
from simreality.social_beliefs import SocialBeliefSystem
from simreality.social_decisions import SocialBeliefDecisionAdapter
from simreality.social_trust import SocialTrustLedger

trust = SocialTrustLedger({("guarded-npc", "witness"): 0.2})
beliefs = SocialBeliefSystem(trust)
beliefs.observe(
    "guarded-npc",
    Evidence("report-1", "guard-was-bribed", "witness", 1, 0.8, 1.0, 40),
)
profile = NPCValueProfile("guarded-npc", {"justice": 0.8, "loyalty": 0.6})
options = [
    ChoiceOption("report-it", {"justice": 0.5, "loyalty": -0.4}),
    ChoiceOption("stay-silent", {"justice": -0.2, "loyalty": 0.3}),
]
result = SocialBeliefDecisionAdapter.rank(
    "guarded-npc", beliefs, profile, options,
    value_effects={"guard-was-bribed": {"justice": 0.7}},
)
preferred = result.preferred
```

## Determinism and boundaries

- The adapter is read-only and does not add evidence or mutate trust.
- The profile must belong to the requested observer.
- Candidate ranking is deterministic; equal scores break ties by choice ID.
- Every belief effect is caller-supplied. The adapter does not infer what a
  claim means, whether it is true, or which choice is morally correct.
- A claim referenced by an effect mapping must already exist in that NPC's
  belief ledger. Missing claims raise `KeyError` instead of being silently
  treated as fact or as an arbitrary confidence.
- Different trust histories, beliefs, value profiles, and bias sensitivities can
  make NPCs rank the same choices differently.

This is an integration layer for simulation logic, not a replacement for action
planning. A future decision cycle can use the selected option to constrain
candidate plans, then record the resulting interaction as a later world event.
