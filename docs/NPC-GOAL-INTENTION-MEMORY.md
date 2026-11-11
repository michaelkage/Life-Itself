# NPC goal intention memory

`GoalIntentionMemoryLedger` is a compact autobiographical projection over
existing authoritative records. It records why an intention entered or left
focus, which goal was committed to, which ambitions were deferred, and what
terminal plan outcomes were observed.

The ledger does not generate narrative motives. Its content comes directly
from a goal lifecycle reason, a commitment rationale, an action-plan outcome,
or an existing owner-specific autobiographical interpretation. Every entry
retains a source kind, source ID, tick, goal owner, and evidence IDs.

## Ingestion

Call `GoalIntentionMemoryAdapter.ingest` with the existing `GoalBook` and
whichever source ledgers are available. The adapter is read-only with respect
to those ledgers and appends deterministic entries to the intention-memory
ledger. Repeating the same ingestion is idempotent. Conflicting reuse of a
source identity is rejected.

Autobiographical memories are linked only when their exact memory IDs appear
in a goal lifecycle event's evidence IDs. No tag similarity or semantic
guessing associates an experience with an ambition.

Commitment records create one `committed` entry for the selected goal and
one `deferred` entry per competing goal. Deferral is not abandonment.
Action-plan outcomes preserve the evaluated plan's evidence event IDs and
distinguish completed, failed, and replanned outcomes.

## Persistence and invariants

`GoalIntentionMemorySnapshot` provides canonical JSON serialization and
restoration. Entries are immutable, append-only, deterministically identified,
and chronologically ordered per NPC and goal. The snapshot is a compact
cross-reference projection; source ledgers remain authoritative and should
also be persisted. Composite saves accept
`SimulationWorldCheckpoint.capture(..., goal_intention_memories=ledger)`
and restore the ledger as `RestoredSimulation.goal_intention_memories`.
Checkpoint validation requires the matching GoalBook and validates each
entry against its lifecycle, commitment, action-plan evaluation, or
autobiographical source ledger. The component is optional, so older
checkpoint payloads remain loadable.

Tests: `tests/test_goal_intention_memory.py` and
`tests/test_world_checkpoint.py`.
