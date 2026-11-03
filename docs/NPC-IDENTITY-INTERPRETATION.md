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


## Relationship-conditioned interpretation

`interpret_with_relationships` adds an optional observer-to-target relationship input.
An `IdentityRelationshipAssociation` explicitly links an event, the NPC whose
identity proposal is being interpreted, the policy, and another person whose
relationship matters. The trust ledger is queried for that exact observer/target
pair; trust 0.5 is neutral, while higher or lower trust contributes according to
the association's signed coefficient and relevance scale.

Unknown trust pairs are neutral. Contributions are recorded with the target ID,
trust sample and resulting adjustment. They are summed with the belief-conditioned
proposal, then clamped to the original per-event delta cap and trait bounds. This
is not a universal judgment about the target and does not automatically accept an
identity change. It simply lets a person the NPC trusts or distrusts influence
how that NPC interprets the same event.


## Personality-conditioned interpretation

`NPCIdentityPersonality` stores caller-defined, normalized personality axes for
one NPC. Projects can model axes such as fearfulness, confidence, stubbornness,
openness, or sociability without the engine imposing a fixed personality
classification. Values are finite and bounded to [-1, 1], and the profile copies
its input mapping into an immutable view.

`IdentityPersonalityRule` explicitly maps one axis to one identity policy with a
signed coefficient. `interpret_with_personality` applies the matching effects
after the interpreter's belief appraisal. Missing profiles or axes are neutral;
duplicate rules and mismatched NPC IDs are rejected. Contributions are returned
for inspection, and the original proposal's delta cap and trait bounds remain in
force. Personality influences interpretation, not automatic acceptance or a
universal moral judgment.



## Unified interpretation pass

`interpret_comprehensively` evaluates belief claims, explicitly associated personal
memories, observer-to-target trust, and personality axes in one pass against the
same original proposal. It records each source's contribution separately and
applies the combined adjustment under the original policy delta cap and trait
bounds. This avoids accidentally recalculating from the original proposal when
several independent context layers are enabled together. Omitted inputs are
neutral; relationship associations require a trust ledger, and memory links
require an available NPC/memory entry. The method is read-only and still leaves
acceptance or rejection to `IdentityDecisionLedger`.


## Individual values

The comprehensive appraisal accepts `NPCIdentityValues`, a normalized, immutable profile of signed priorities such as loyalty, fairness, freedom, or duty. `IdentityValueRule` explicitly maps a value axis to a policy and supplies the signed coefficient. No value is inherently good or bad in the engine: its influence depends on the authored policy mapping. Contributions are reported separately, missing axes are neutral, and the combined result remains bounded by the original proposal cap.
