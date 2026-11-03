# Witness-specific event recall

The authoritative world-event ledger remains the objective record. Witness recall
is a separate, lossy projection: it selects only explicitly declared event
attributes and never changes the event or invents a fact.

## Inputs and determinism

- `RecallDetail` maps a stable detail ID to an existing scalar event attribute,
  category, and authored salience.
- `WitnessRecallProfile` supplies category attention multipliers, encoding
  strength, and a recall threshold.
- The caller supplies one seeded encoding sample per detail. No global random
  state or wall clock is read.
- Repeating an event/witness request with the same samples returns the cached
  record. Conflicting samples for the same pair are rejected.

Recall confidence is `min(1, salience × attention × encoding_strength)`.
A detail is encoded only if its supplied sample is at most that confidence and
the confidence meets the profile threshold. This is a transparent reference
heuristic, not a psychological claim.

## Boundaries and next integration

Only IDs already listed as event witnesses can generate recall. The output
preserves event ID and tick, and separately lists omitted details. It does not
modify NPC memories, legal evidence, rumours, or beliefs; adapters can consume
the recall record explicitly. Current recall cache is in-memory; durable
serialization and integration with memory decay remain follow-up work.
