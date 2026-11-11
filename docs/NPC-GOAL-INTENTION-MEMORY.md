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


## Bounded intention recall

`GoalIntentionRecallAdapter` retrieves only memory entries owned by the NPC
and linked to a goal through the intention-memory ledger. It does not interpret
the prose in `content`, infer causality, or transfer one NPC's experience to
another. A caller must supply one `GoalIntentionRecallRule` per goal whose
remembered experience should affect arbitration.

Each rule explicitly assigns a signed weight to exact memory types, for example
`plan_failed`, `plan_completed`, or `personal_experience`. Weights are
bounded to [-0.25, 0.25], decay by a configurable half-life, and aggregate to
a per-goal adjustment capped by `max_adjustment` (also at most 0.25). The
result exposes every contributing memory ID, age, authored weight, and decayed
contribution. Unweighted memories have no influence. No default emotional or
moral interpretation is applied.

`GoalIntentionContinuityAdapter.reconsider` accepts
`intention_memories` and `recall_rules`. It combines recalled adjustments
with explicitly supplied experience adjustments, clamps the combined influence
to the existing [-0.25, 0.25] evaluator contract, and performs fresh arbitration.
The recall digest is included in the arbitration assessment identity, so
changing relevant evidence after a decision cannot silently replay or fork the
same NPC/tick commitment. The returned `GoalContinuityResult.intention_recall`
provides the complete evidence trail.

Recall is a bounded appraisal input, not a goal lock. A previously failed
approach can reduce an ambition's score when its authored rule says so, but
current needs, deadlines, resources, and stronger competing goals can still
change the selected intention. Deferred goals remain active.

Tests: `tests/test_goal_intention_recall.py`.


When the existing autobiographical and experience-transfer ledgers are supplied,
recall also consumes exact `goal:success` / `goal:failure` tag matches from
`NPCGoal.metadata["experience_tags"]`. It preserves source classes as
`personal`, `witnessed`, and `reported`; reported accounts retain their
transfer confidence discount. This reuses the engine's existing strategic
experience projection rather than converting another NPC's report into a
personal memory. If the same first-hand memory is already linked through the
intention ledger, it is counted once per goal, not twice.
