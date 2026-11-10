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

This module is deliberately an advisory bridge and explicit application layer.
Policy authoring determines what an identity axis means for a goal category;
the engine does not infer psychological meaning from trait names.
