# NPC goal emergence and lifecycle

`npc_goal_emergence.py` adds a deterministic proposal stage on top of the
existing `GoalBook`. It does not silently create goals or change intentions.

## Explicit trigger rules

Each `GoalEmergenceRule` maps one authored `GoalTemplate` to one or more
named signals:

- a need deficit (for example, `safety >= 0.7`);
- an emotional intensity (for example, `grief >= 0.6`);
- a stress adaptation channel (for example, `sleep_priority >= 0.5`);
- an exact autobiographical or strategic-experience tag.

Thresholds are normalized to [0, 1]. No free-text semantic inference or
randomness is involved. Future emotional/stress samples and future memories
are rejected or excluded. Strategic experience evidence must belong to the
same NPC and not post-date the proposal tick. Its source class remains visible
as personal, witnessed, or reported; reported accounts are not converted into
personal memories. Rules requiring a turning point require an actual
turning-point autobiographical memory.

## Proposal and adoption

`NPCGoalEmergence.propose(...)` is read-only. Stable IDs are derived from
owner, rule, and template identity, so repeated evaluation of the same rule
does not generate new IDs. An active/completed matching template is not
proposed again. A caller explicitly adopts a proposal with
`GoalBook.add(proposal.to_goal())`. The resulting goal records its proposal
and template IDs in metadata.

Existing goals continue to compete through the normal GoalBook ranking and
bounded motivational adjustments. Proposal generation does not override
obligations or select actions.

## Lifecycle history

`GoalLifecycleLedger` records append-only, deterministic transitions:
adoption, status changes, suspension/blocking, retirement, and reopening
where the prior status permits it. Each event retains the reason and evidence
IDs. Completed and failed goals cannot be reopened in this ledger; abandoned
or blocked goals can transition back to active when the caller explicitly
records that change. The ledger is currently an in-memory snapshot API and is
not yet wired into composite world-checkpoint persistence.

This keeps three decisions separate: evidence suggests an intention, an NPC
or higher-level policy adopts it, and a later lifecycle decision changes its
status. A retired goal is never erased from history.
