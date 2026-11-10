# NPC relationship facets

Relationships are directed: A's relationship toward B is not B's relationship
toward A. The ledger stores independent facets rather than a single affinity,
alignment, or good/bad score:

- warmth
- resentment
- rivalry
- obligation
- dependence
- respect
- fear
- comfort

Each facet is bounded to [-1, 1]. Positive and negative changes are explicit,
event-linked evidence supplied by the simulation or gameplay systems. A facet
can coexist with its apparent opposite: an NPC can feel warmth and resentment,
or respect and fear, at the same time. Changes to one facet never erase another.

The ledger does not infer feelings from co-location, familiarity, trust, or
agreement. Those systems remain separate. Each change has a stable ID, source
world-event ID, observer, target, tick, facet, delta, and optional evidence tag.
Replaying an identical ID is idempotent; conflicting reuse is rejected.
Snapshots preserve the complete history and replay order. Composite world
checkpoints validate source-event existence, participants, and chronology.

This is a simulation substrate, not an automatic personality verdict. Higher
level NPC appraisal and decision policies decide what evidence means to each
individual and whether/how it should change a relationship.
