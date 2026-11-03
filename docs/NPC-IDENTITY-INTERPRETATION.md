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

Belief ledgers can be supplied directly, or callers can use
`interpret_from_social_beliefs(proposals, social_beliefs)` to consume the public
observer-specific snapshots from `SocialBeliefSystem`. That path preserves the
trust reliability sampled when each NPC originally heard the evidence; later
relationship changes do not rewrite that observation. The adapter is read-only
and does not reach into the belief system private state.

Rule coefficients and claim meanings remain authored simulation data, not
universal moral judgments. Regression coverage includes two NPCs who hear the
same report from a source they trust differently.


## Memory-conditioned interpretation

`interpret_with_memories` combines the existing belief-conditioned result with
explicitly authored `IdentityMemoryAssociation` links. Each link names the
specific event, NPC, identity policy and memory index; the system never guesses
which past experience is relevant. A memory contributes its current retention
multiplied by a signed coefficient and a bounded relevance scale. Multiple
linked memories are summed, then the original policy delta cap and trait bounds
are applied. The returned result records memory index, retention and contribution
for inspection. Missing associations are neutral; invalid memory indices fail
rather than silently selecting another memory. This is an appraisal input only,
not an automatic identity decision.
