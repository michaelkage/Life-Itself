# Repeated cognitive dissonance and identity evolution

`DissonanceIdentityBridge` connects the cognitive dissonance ledger to the existing gradual identity proposal and explicit identity decision systems.

## Authored mapping

A `DissonanceIdentityRule` explicitly maps one conflict kind to one identity axis and signed coefficient. It also defines a minimum number of conflicts and a small maximum trait delta. There is no universal assumption that conflict makes an NPC more or less trusting, loyal, fearful, or open; the simulation author chooses the axis and direction.

The bridge receives conflict records, current `NPCIdentityProfile` values, and explicit mappings from each conflict to its authoritative world event and from each NPC to participant/witness role. It aggregates unresolved conflict pressure for each owner/policy/axis, requires the configured repetition threshold, and emits a bounded `IdentityChangeProposal`.

## Explicit acceptance remains mandatory

The bridge is read-only. It does not update traits. Feed the resulting proposal to `IdentityDecisionLedger.decide` to preserve the NPC's ability to accept or reject it. Rejection leaves identity unchanged; acceptance changes the trait only through the existing replay-safe identity ledger.

Use only unresolved conflicts when calling the bridge (for example, `CognitiveDissonanceLedger.unresolved(npc_id)`). Resolve each accepted/rejected proposal through the cognitive dissonance response ledger separately. The bridge does not mark conflicts resolved automatically.

Tests: `tests/test_dissonance_identity.py`.
