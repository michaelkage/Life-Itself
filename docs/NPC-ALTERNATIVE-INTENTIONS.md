# NPC Alternative Intention Formation

`GoalAlternativeEvaluator` connects a current active intention to the existing authored `GoalEmergenceRule` system. It returns read-only candidate alternatives when a different goal category is supported by explicit need, emotion, stress, or experience evidence. It does not infer semantic intent or alter the GoalBook.

`GoalAlternativeAdapter.adopt` is the explicit acceptance boundary. It revalidates the source goal state, creates the candidate as a distinct goal, and records its adoption and evidence in `GoalLifecycleLedger`. The original goal remains active and unchanged. This is deliberate: adopting a new possibility is not proof that the NPC has abandoned an existing ambition.

Event-driven obsolescence remains handled by `GoalReviewEvaluator` and authored `GoalReviewPolicy` rules. Configure exact event types, participant ownership, goal category, required attributes, and an explicit `ABANDON` or `REFRAME` action. The resulting review proposal must still pass through `GoalReviewDecisionLedger` and `GoalReviewApplicationAdapter`.

## Example

    alternatives = GoalAlternativeEvaluator.assess(
        goals, "career-goal", tick, rules=emergence_rules,
        need_deficits=need_deficits, history=life_history,
    )
    # NPC decision layer selects a proposal explicitly.
    adopted_goal, lifecycle_event = GoalAlternativeAdapter.adopt(
        selected_proposal, goals, lifecycle,
    )

The alternative proposal retains the underlying emergence proposal, including trigger types, evidence IDs, source classes, authored rule ID, and proposed tick. Adoption is idempotent for the same proposal when its lifecycle record already exists. A stale source goal or conflicting goal ID is rejected.


## Combined intention assessment

GoalIntentionEvaluator.assess runs the authored event-review policies and goal-emergence rules against the same current GoalBook and returns separate review_proposals and alternatives. A permanent world event can recommend abandoning an obsolete goal while current needs or experience independently suggest a different goal. Neither proposal accepts itself, and an obsolescence recommendation does not suppress alternative evidence.
