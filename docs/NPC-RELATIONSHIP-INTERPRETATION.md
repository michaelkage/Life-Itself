# Individual NPC interpretation and relationship evolution

The authoritative world event records what happened. It does not prescribe what
the event means. `NPCRelationshipInterpreter` converts explicit, observer-owned
inputs into that observer's directed relationship changes.

Each `RelationshipInterpretationProfile` belongs to one observer and maps:
- value-impact axes to relationship facets;
- bias cues to relationship facets;
- optional claim IDs to relationship facets, weighted by that observer's own
  belief confidence.

The caller supplies the event's value impacts and the bias cues available to
that observer. The adapter never infers those inputs from event labels, roles,
or a universal moral model. Belief confidence is centered at 0.5: uncertainty
contributes zero, confidence above 0.5 contributes in the mapped direction,
and confidence below 0.5 reverses it.

Different profiles can therefore produce opposite reactions to the same event.
A witness can become warmer and more resentful at once. This is not a single
approval score, and it does not change the authoritative event, trust, or
another observer's interpretation.

Interpretations require a recorded witness, an event participant as target,
and a profile owned by the observer. Stable event/observer/target/facet IDs store a complete facet vector, including
zero-valued facets. This makes replay idempotent and lets a restored relationship
ledger reject a conflicting interpretation even after the interpreter itself is
recreated. The resulting
`SocialRelationshipLedger` is already supported by composite world checkpoint
persistence and source-event validation.
