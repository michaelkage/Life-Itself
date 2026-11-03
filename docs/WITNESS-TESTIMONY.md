# Witness testimony and memory decay

Witness recall now has a downstream testimony ledger. A caller converts a
`WitnessRecall` into an immutable `TestimonyRecord`, preserving event/witness
provenance, recalled details, and explicitly omitted details. Accounts have
stable IDs: identical replay is idempotent and conflicting ID reuse is rejected.

Each detail's confidence decays from its original confidence and recording time:
`C(t) = C₀ × exp(-k × (t - t₀))`. This is computed absolutely, not tick by tick,
so save frequency cannot alter confidence. The caller chooses the decay rate;
the ledger does not infer emotional trauma or credibility.

`TestimonyLedger.to_json/from_json` provide canonical versioned persistence.
This layer is separate from NPCMemory and does not mutate objective events,
identity, beliefs, or legal outcomes. It can support later dialogue, investigation,
and contradiction analysis.
