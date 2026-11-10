# Identity-driven NPC goal reassessment

An accepted identity change can make an existing intention feel less relevant,
more important, or different in meaning. The simulation must not infer that
accepting an identity change also means accepting a goal change.

## Flow

1. `IdentityGoalAlignmentAdapter` receives explicit identity decisions.
2. Rejected identity decisions are ignored. Only accepted decisions are
   considered.
3. Explicit `IdentityGoalAlignmentPolicy` entries match an identity axis,
   goal category, and minimum absolute trait delta.
4. The adapter returns deterministic, read-only
   `IdentityGoalReviewProposal` records. The GoalBook is unchanged.
5. The NPC separately accepts or rejects each proposal by recording an
   `IdentityGoalReviewDecision`.
6. `IdentityGoalReviewDecisionLedger.apply_accepted` applies an accepted
   proposal once, after verifying the goal still has the exact category,
   priority, and confidence that were reviewed.

## Example

```python
from simreality import (
    IdentityGoalAction, IdentityGoalAlignmentAdapter,
    IdentityGoalAlignmentPolicy, IdentityGoalReviewDecision,
    IdentityGoalReviewDecisionLedger, IdentityGoalReviewSnapshot,
)

policy = IdentityGoalAlignmentPolicy(
    policy_id="ambition-career-review",
    identity_axis="ambition",
    goal_category="career",
    action=IdentityGoalAction.REPRIORITIZE,
    minimum_abs_delta=0.15,
    priority_delta=1.0,
)
adapter = IdentityGoalAlignmentAdapter(goal_book, (policy,))
proposals = adapter.assess(identity_decisions.entries(), current_tick=tick)

decisions = IdentityGoalReviewDecisionLedger()
for proposal in proposals:
    # The caller obtains this explicit choice from the owning NPC decision system.
    decision = IdentityGoalReviewDecision(
        decision_id=f"goal-choice:{proposal.proposal_id}",
        proposal=proposal,
        accepted=npc_accepts(proposal),
        decision_tick=tick,
        rationale="NPC's stated reason",
    )
    decisions.record(decision)
    if decision.accepted:
        decisions.apply_accepted(decision.decision_id, goal_book)

saved = IdentityGoalReviewSnapshot.capture(decisions).to_json()
restored_decisions = IdentityGoalReviewSnapshot.from_json(saved).restore()
```

## Guarantees and boundaries

- Rejected identity decisions produce no goal proposals.
- An accepted identity decision is not blanket consent to alter goals.
- Goal proposals retain identity decision ID, source event, identity policy,
  axis, delta, target goal, and alignment policy provenance.
- Rejected goal proposals remain in the append-only decision history and cannot
  be applied.
- Accepted changes are idempotent: the same decision cannot apply twice.
- A proposal is rejected as stale if its goal category, priority, or confidence
  changed after assessment; a fresh review is then required.
- Reprioritization is clamped at zero; confidence remains in [0, 1].
- Reframing changes only the goal category. Abandonment uses the GoalBook's
  terminal-status API. Persist records acceptance without changing the goal.
- `IdentityGoalReviewSnapshot` stores decisions and exactly-once application
  markers in canonical JSON, so a restored ledger does not reapply completed
  changes.

`SimulationWorldCheckpoint.capture` now persists the goal-review ledger alongside the GoalBook and identity-decision ledger. Checkpoint validation requires every review to reference an accepted identity decision for the same NPC, source event, policy, axis, and delta; the source event role and all review timestamps are checked again during restore. Legacy checkpoints remain valid because the new field is optional.\n\nThis module is deliberately an advisory bridge and explicit application layer.
Policy authoring determines what an identity axis means for a goal category;
the engine does not infer psychological meaning from trait names.


## Downstream planning and daily-life integration

An accepted goal review changes the existing GoalBook; it does not directly
execute an action or force a routine. The existing decision and daily-life
adapters consume that updated state on their next assessment:

1. IdentityGoalReviewDecisionLedger.apply_accepted applies the separately
   accepted change exactly once, after its stale-state checks.
2. NPCDecisionCycle.decide reads the same GoalBook and ranks its currently
   actionable goals. A changed priority can therefore change which goal is
   considered first on the next decision tick.
3. The planner still requires an explicit desired-facts mapping and a valid
   sequence of actions with satisfied preconditions. If the highest-ranked
   goal cannot be planned, the cycle tries lower-ranked actionable goals.
4. GoalLifeAdapter.assess can translate the updated active-goal ranking into
   advisory routine-priority proposals. It still checks available time,
   resources, confidence, stress, obligations, social support, and setbacks.
   It does not edit the routine schedule or execute the activity.

The integration is deliberately pull-based: the planner and daily-life adapter
read the canonical GoalBook when called. No extra priority cache needs to be
synchronized, and a restored checkpoint's GoalBook priorities are immediately
visible to those consumers. The identity-goal decision snapshot preserves
review provenance and exactly-once markers; the world checkpoint restores the
goal book and review history as separate, coordinated components.

The regression suite includes an end-to-end planning test proving that a
separately accepted goal review changes the next selected plan, and a rejection
test proving that a rejected review leaves the planning choice unchanged.
