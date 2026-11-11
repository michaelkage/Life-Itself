# Evidence-Based NPC Goal Reviews

NPC intentions should evolve when life changes, but the simulation should not
silently decide what an NPC now wants. This module adds a deterministic,
read-only review layer between authoritative world events and goal changes.

## How it works

A `GoalReviewPolicy` explicitly maps:
- a world-event type,
- a goal category,
- an optional set of exact event-attribute matches,
- a review action,
- optional priority and confidence adjustments,
- and, for a reframe, a target category.

The supported actions are:

| Action | Meaning |
| --- | --- |
| `persist` | Evidence supports continuing to pursue the existing goal |
| `reprioritize` | Suggest a different priority and/or confidence |
| `pause` | Suggest temporarily stepping back |
| `reframe` | Suggest pursuing a related goal under a different category |
| `abandon` | Suggest giving up the goal |

The evaluator only considers active goals owned by event participants. It also
checks the goal's `review_tick`, so evidence older than the goal's most recent
review point cannot prompt another review. Results are ordered by event,
owner, goal, and policy identifiers.

## Example

```python
from simreality.goal_review import (
    GoalReviewAction, GoalReviewEvaluator, GoalReviewPolicy,
)

policies = (
    GoalReviewPolicy(
        policy_id="career-setback",
        event_type="promotion_denied",
        goal_category="career",
        action=GoalReviewAction.REPRIORITIZE,
        priority_delta=-1.5,
        confidence_delta=-0.1,
        required_attributes=(("department", "engineering"),),
    ),
    GoalReviewPolicy(
        policy_id="career-pivot",
        event_type="business_opportunity",
        goal_category="career",
        action=GoalReviewAction.REFRAME,
        target_category="entrepreneurship",
    ),
)
reviewer = GoalReviewEvaluator(goal_book, policies)
proposals = reviewer.assess(world_events)
```

The returned proposals include the current and suggested values. They do not
change the `GoalBook`, status, progress, or routine schedule. The caller must decide whether the NPC accepts a proposal. The
`GoalReviewDecisionLedger` records either acceptance or rejection, along with
the decision tick and an explicit rationale. Recording a decision does not
silently apply the proposed change to the GoalBook; a later goal-management
step must apply accepted changes through the normal goal API.

## Determinism and boundaries

- No randomness, hidden inference, or implicit event-to-intention mapping.
- Events must have unique IDs within an assessment batch.
- Exact configured attributes are required when a policy specifies them.
- A policy cannot reframe without an explicit target category.
- Priority suggestions are clamped at zero; confidence suggestions are clamped
  to the valid 0–1 range.
- Repeating an assessment with the same inputs returns the same proposals.
- The evaluator is read-only; it does not own replay state or persist decisions.
- The decision ledger is append-only, idempotent for identical decision IDs, and
  rejects conflicting reuse or multiple decisions for the same proposal.
- `GoalReviewDecisionSnapshot` stores the decision history in canonical JSON;
  restoring it recreates the same ordered ledger.

This is an advisory layer plus a persistent decision record, not an autonomous
goal mutation system. The authoritative world-event bridge can later materialize
these decisions as world events, while accepted changes remain a separate,
explicit goal-management operation.

## Decision history and checkpoints

`GoalReviewDecisionLedger` stores one accepted or rejected decision per review
proposal. Each record preserves the source event, NPC, goal, policy, proposed
change, decision tick, and rationale. Identical retries with the same decision
ID are harmless; reusing an ID with different content or attempting a second
decision for the same proposal is rejected. The ledger does not apply accepted
changes automatically.

`GoalReviewDecisionSnapshot` provides canonical JSON save/load. It is also an
optional section of `SimulationWorldCheckpoint`: when included, the checkpoint
requires the matching GoalBook, verifies each referenced goal and owner, checks
the source event exists and names the NPC as a participant, and rejects
future-dated decisions. Older checkpoints without this optional section remain
readable.


## Applying accepted decisions

`GoalReviewApplicationAdapter` is the explicit mutation boundary. It
accepts only an accepted `GoalReviewDecision` and checks that the goal
still belongs to the recorded NPC, remains active, has not been reviewed after
the decision tick, and still matches the category, priority, and confidence
captured by the proposal. Stale decisions fail without changing the goal.

- `reprioritize` applies the proposed priority and confidence.
- `reframe` applies the proposed category, priority, and confidence.
- `abandon` requires a `GoalLifecycleLedger` and records the
  source event as lifecycle evidence.
- `persist` records the reviewed confidence and advances the review tick.
- `pause` is recorded as an accepted review, but remains non-suspending:
  the goal model has no paused status, and pause must not be misrepresented as
  dependency-derived `blocked`.

`GoalReviewApplicationLedger` makes retries idempotent by decision ID.
`GoalReviewApplicationSnapshot` provides canonical JSON persistence.
Application history is deliberately a separate component: recording a decision
is not the same operation as applying it, and old decision snapshots remain
compatible. The simulation owner should checkpoint the application snapshot
alongside the decision ledger and GoalBook.
