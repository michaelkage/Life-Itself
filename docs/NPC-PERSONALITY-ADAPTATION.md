# Memory-Grounded Personality Adaptation

`PersonalityAdaptationRule` explicitly connects one autobiographical memory tag to one named personality axis. Axes are project-defined normalized values in [-1, 1]; the engine does not impose a universal personality taxonomy.

The adapter considers only memories owned by the NPC whose tags exactly match the rule. Every matching memory contributes:

`identity_impact × memory salience`

Salience uses the existing life-history half-life. Turning-point memories retain their existing full-salience behavior. The rule coefficient supplies the authored direction and strength; the sum is capped by `maximum_delta`, and the resulting trait remains inside [-1, 1]. A minimum number of memories is required by default, preventing a single event from immediately rewriting a personality axis. An optional minimum evidence threshold can demand stronger accumulated experience.

The proposal includes every contributing memory ID, source event, tick, signed identity impact, salience, and weighted contribution. It uses the latest contributing event as its proposal event reference and requires the caller to supply whether the NPC was a participant or witness. It does not infer that role.

## Agency and persistence

`PersonalityAdaptationAdapter.propose` is read-only. It returns ordinary `IdentityChangeProposal` values, which can be explicitly accepted or rejected through the existing `IdentityDecisionLedger`.

- Accepted proposals update the relevant axis once and become part of the decision history.
- Rejected proposals remain recorded without changing the axis.
- Identity decision snapshots already preserve accepted trait state and rejected decisions for save/restore.

The adaptation rules are authored configuration and must be reattached after loading. The autobiographical memories are persisted with `life_history`; the resulting trait decisions use the existing identity-decision persistence path.

This is gradual evidence-driven adaptation, not automatic personality mutation. Different NPCs can use different rules, thresholds, coefficients, and half-lives for the same experiences.

Tests: `tests/test_personality_adaptation.py`.
