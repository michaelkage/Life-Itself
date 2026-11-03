# Belief-conditioned NPC identity interpretation

The identity evolution evaluator creates bounded, event-specific proposals. This
layer allows the same proposal to be interpreted differently by different NPCs
using their own belief ledgers.

## Explicit interpretation rules

An `IdentityInterpretationRule` connects an identity policy to a named belief
claim and a signed coefficient. The claim's confidence is centered around 0.5:

- Confidence 0.5 contributes zero.
- Confidence 1 contributes the positive coefficient.
- Confidence 0 contributes the negative coefficient.

Contributions from all rules matching a policy are summed and added to the
proposal's existing trait delta. The result is clamped to the original policy's
per-event delta cap and the trait's [-1, 1] bounds. Missing NPC ledgers or claims
are neutral; the system does not invent beliefs.

The returned `InterpretedIdentityChange` keeps the original proposal, interpreted
proposal, and each claim's confidence/contribution together for inspection.

## Decision boundary

Interpretation is not acceptance. The interpreter never mutates an NPC profile
or decision ledger. The caller presents the interpreted proposal for an explicit
accept/reject decision through `IdentityDecisionLedger`. This keeps belief,
identity, and agency separate: what an NPC believes can change how an event feels,
but does not silently rewrite who that NPC becomes.

Belief ledgers can be supplied from the existing observer-specific
`SocialBeliefSystem` / `BeliefLedger` pipeline. Rule coefficients and claim
meanings remain authored simulation data, not universal moral judgments.
