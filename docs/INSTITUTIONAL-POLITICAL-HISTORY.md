# Institutional political history

`simreality/institutional_politics.py` records how an institution's internal
politics can evolve across periods. It is an event-sourced state model, not an
automatic story generator.

## Recorded effects

Each `InstitutionalPoliticalEvent` may explicitly change:

- a department's influence (bounded from 0 to 1);
- the relationship between two departments (signed from -1 rivalry to +1 alliance);
- one leadership priority (bounded from 0 to 1).

The event's rationale is retained as part of its identity. The system does not
infer that departments are allies because they share a goal, or rivals because
they compete for resources. A caller or another simulation system must record
the event and its effects.

## Determinism and replay

Events are replayed in canonical `(period_index, event_id)` order. Replaying
the same event set therefore produces the same state regardless of append order.
Repeated identical event IDs are idempotent; reusing an ID with different
content is rejected. Influence, relationships, and leadership priorities are
clamped to their documented ranges.

The ledger supports a versioned dictionary snapshot and restoration. It is
also integrated as the optional `institutional_politics` section of
`SimulationWorldCheckpoint.capture(...)`; restored worlds expose
`RestoredSimulation.institutional_politics`. Existing checkpoints remain
compatible when the optional section is absent.

## Boundaries and future integration

The ledger stores outcomes, not the social process that creates them. It does
not yet model lobbying conversations, coalition bargaining, leadership
succession, departmental mergers, policy execution, or the downstream effects
of resource allocations. Those systems can emit political events later, while
this ledger remains the canonical history and replay boundary.
