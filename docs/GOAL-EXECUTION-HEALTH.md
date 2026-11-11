# Persistent NPC Goal Execution Health

GoalExecutionHealthEvaluator turns repeated authoritative plan outcomes into read-only goal-review proposals. It does not change a goal, cancel work, or infer that an NPC has changed their intention.

## Evidence and decision boundary

- It consumes ActionPlanEvaluationLedger.plan_history and the same WorldEventLedger used by action execution.
- Only terminal failed plan evaluations count. A replanned plan is neutral because superseding work is not proof of infeasibility.
- A completed plan resets the consecutive failure streak.
- Each authored rule sets a minimum consecutive failure count and minimum simulation-tick observation window. One failure cannot trigger review.
- Proposals retain all underlying evidence event IDs and exact first/latest observation ticks.
- to_goal_review_proposal adapts the assessment to the existing decision/application pipeline. Preserve the richer health proposal alongside the decision for complete multi-event audit provenance; the legacy decision schema anchors its event reference to the latest evidence event.

Temporary blockers remain execution/replanning concerns. Authored GoalReviewPolicy event rules remain the mechanism for explicit world-event obsolescence, such as a unique target being permanently removed. Neither mechanism silently overwrites an intention.

## Example

    rules = (GoalExecutionHealthRule("career-infeasible", "career", 3, 24),)
    evaluator = GoalExecutionHealthEvaluator(goals, evaluations, events, rules)
    for assessment in evaluator.assess():
        review_proposal = assessment.to_goal_review_proposal()
        # The NPC decision system explicitly accepts or rejects the proposal.
