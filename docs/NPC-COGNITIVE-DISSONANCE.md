# NPC cognitive dissonance and psychological conflict

The cognitive dissonance ledger records explicit contradictions experienced by an individual NPC. It does not decide which belief is true and does not infer hidden motives or actions.

## Declaring conflict

Create a `DissonanceInput` with a stable conflict ID, owner, kind, descriptive text, two references, commitment strength, evidence confidence, relevance, and tick.

- `belief_conflict` represents two caller-declared claims or attitudes that the simulation says are in tension.
- `commitment_violation` represents a caller-declared action that conflicts with a stated commitment.
- Score is the product of commitment strength, evidence confidence, and relevance. Every factor is bounded to [0, 1], so the score is also bounded.
- Inputs are owner-specific. The same event can produce different assessments for different NPCs by supplying different individual commitment strengths or relevance.

## Explicit responses

`CognitiveDissonanceLedger.decide` records one response per conflict: `rationalize`, `avoid`, `seek_evidence`, `acknowledge`, or `reconsider`. The response and rationale are history only. Even `reconsider` does not silently alter beliefs, values, conditioning, or identity; the caller must separately submit any proposed change through the relevant explicit decision system.

Conflicts and decisions are append-only and replay-safe. Identical IDs and payloads are idempotent; conflicting reuse is rejected. Decisions must belong to the conflict owner and cannot precede the conflict tick. Unresolved conflicts remain queryable per NPC.

## Persistence

`CognitiveDissonanceSnapshot` provides schema-versioned canonical JSON capture, validation, and restore. This standalone component can be persisted alongside a world checkpoint by the host. It is not yet wired into `SimulationWorldCheckpoint`; no existing checkpoint schema is changed by this module.

Tests: `tests/test_cognitive_dissonance.py`.
