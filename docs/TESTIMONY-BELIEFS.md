# Testimony and NPC belief integration

`TestimonyBeliefAdapter` turns an investigation report into explicit claims
and source-attributed evidence for one observer.

- Each reported detail value is a proposition scoped to its event and attribute.
- Each witness contributes evidence for the value they reported; conflicting values
  become competing propositions rather than an automatic verdict.
- Evidence strength is the reported, time-decayed testimony confidence multiplied
  by a configurable scale.
- Source reliability is resolved by `SocialBeliefSystem` from the observer's
  relationship trust at observation time.
- Evidence IDs include account, attribute, value, and observer, making repeated
  application idempotent through the existing belief ledger.
- The adapter does not infer truth, accuse anyone, or directly modify goals,
  identity, or behavior. Downstream decisions can inspect resulting beliefs.

The integration is deliberately explicit: callers choose the observer and
observation tick and decide when an investigation report is shared with them.
