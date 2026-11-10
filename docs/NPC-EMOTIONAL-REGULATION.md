# NPC emotional regulation, expression, and decision influence

The emotional event ledger represents what an NPC feels. This module adds two
separate, read-only projections: what the NPC outwardly displays and how emotion
can contribute to an authored decision consideration.

## Suppression and expression

`EmotionalRegulationProfile` is owner-specific. Its suppression coefficient
ranges from 0 to 1 for each emotion axis:

- 0 displays the full intensity.
- 1 conceals the full intensity.
- Intermediate values display the remaining proportion.

`EmotionalExpressionAdapter.project` returns felt, displayed, and concealed
intensities. It never mutates the emotional ledger. Unlisted axes have no
suppression, so individual emotional profiles need not enumerate every emotion.

Conflicting feelings coexist independently. An NPC may feel affection and
resentment simultaneously, and may display one more strongly than the other.

## Decision influence

`EmotionalDecisionRule` explicitly maps an emotion axis to a named decision
consideration with a signed coefficient. `EmotionalDecisionAdapter.assess`
returns each contribution, the total emotional delta, and a bounded adjusted
score. It does not select, execute, or veto an action. The caller retains
responsibility for combining this score with values, beliefs, goals, risks, and
other decision inputs.

## Scope

Suppression is currently a deterministic expression projection, not a
psychological diagnosis or a resource-consuming willpower simulation. The
existing event ledger provides additive emotional buildup and configurable
decay; this module does not rewrite that history or alter long-term identity.

Tests: `tests/test_emotional_regulation.py`.
