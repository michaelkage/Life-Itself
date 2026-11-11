# NPC goal emergence and lifecycle persistence

The goal-emergence layer produces deterministic proposals from authored rules.
It does not mutate the GoalBook. The caller adopts a proposal explicitly with
`GoalBook.add(proposal.to_goal())`.

A proposal rule can match normalized need deficits, emotional intensities,
stress-adaptation channels, or exact autobiographical/strategic-experience
tags. Evidence is bounded by the decision tick and keeps its provenance
(personal, witnessed, or reported). A rule that requires a turning point must
match a personal autobiographical memory marked as a turning point.

## Reconsideration and replacement

Existing intentions remain in the same GoalBook and compete under normal goal
ranking. Matching active or otherwise non-terminal template instances suppress
duplicate proposals. If a prior instance was abandoned or failed, a new
deterministic incarnation receives a distinct goal ID. An abandoned intention
can instead be explicitly reactivated with `GoalBook.reopen(goal_id, tick)`;
blocked intentions can resume when their prerequisites recover. Completed and
failed intentions remain terminal.

The caller records every adoption or status transition in
`GoalLifecycleLedger`, including a reason and evidence IDs. Use
`ledger.transition(goal_book, goal_id, target_status, tick, reason, ...)` to
apply supported status changes atomically with lifecycle recording. The first
transition bootstraps an active-goal record; identical retries are idempotent.
The ledger enforces owner continuity, non-decreasing ticks, and legal
transitions. It retains the sequence of adoption, blocking, abandonment, and
reopening events. It does not silently mutate GoalBook state outside this
explicit API.

## Checkpoint integration

`GoalLifecycleSnapshot` is a canonical component codec. The composite
`SimulationWorldCheckpoint.capture(..., goal_book=..., goal_lifecycle=...)`
persists it as the optional `goal_lifecycle` section. Restore validates that
every lifecycle record refers to a saved goal and owner, predates neither goal
creation nor the checkpoint tick, and that each goal's latest lifecycle status
matches its saved GoalBook status. Evidence references must resolve to saved
autobiographical memories or saved experience-transfer IDs.

The new checkpoint section is optional, so older checkpoint JSON remains
readable without a lifecycle ledger. To restore a complete goal history,
persist the GoalBook and lifecycle ledger together.
