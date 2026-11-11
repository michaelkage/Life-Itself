"""Regression tests for persistent goal execution health assessments."""
import unittest
from simreality.action_evaluation import ActionPlanEvaluationLedger
from simreality.action_execution import ActionExecutionLedger
from simreality.goal_execution_health import GoalExecutionHealthEvaluator, GoalExecutionHealthRule
from simreality.goal_review import GoalReviewAction
from simreality.goals import GoalBook, NPCGoal
from simreality.planning import DeterministicPlanner, PlanningAction
from simreality.world_events import WorldEventLedger

class GoalExecutionHealthTests(unittest.TestCase):
    def setUp(self):
        self.events = WorldEventLedger()
        self.planner = DeterministicPlanner((PlanningAction("attempt", frozenset({"ready"}), frozenset({"done"})),))
        self.executions = ActionExecutionLedger(self.planner, (), self.events)
        self.evaluations = ActionPlanEvaluationLedger(self.executions)
        self.goals = GoalBook()
        self.goals.add(NPCGoal("goal", "npc", "career", 5.0, review_tick=0, confidence=0.8))

    def fail_plan(self, plan_id, tick):
        execution_id = plan_id + ":step:0"
        self.executions.start(execution_id, "npc", tick, "attempt", {"ready"}, {}, plan_actions=("attempt",))
        self.executions.cancel(execution_id, tick + 1, "temporary precondition became unavailable")
        self.evaluations.evaluate(execution_id)
        self.evaluations.register_plan(plan_id, "npc", "goal", ("attempt",), {"never-observed"})
        self.evaluations.evaluate_plan(plan_id, "failed")

    def evaluator(self, failures=2, window=5):
        return GoalExecutionHealthEvaluator(self.goals, self.evaluations, self.events,
            (GoalExecutionHealthRule("persistent", "career", failures, window, priority_delta=-2.0),))

    def test_single_failure_is_not_a_review(self):
        self.fail_plan("p1", 2)
        self.assertEqual(self.evaluator().assess(), ())

    def test_repeated_failures_propose_with_complete_evidence_without_mutation(self):
        self.fail_plan("p1", 2)
        self.fail_plan("p2", 8)
        before = self.goals.snapshot()
        proposal, = self.evaluator().assess()
        self.assertEqual(proposal.consecutive_failed_plans, 2)
        self.assertEqual(proposal.latest_failure_tick, 9)
        self.assertEqual(len(proposal.evidence_event_ids), 4)
        self.assertEqual(proposal.proposed_priority, 3.0)
        self.assertEqual(self.goals.snapshot(), before)
        self.assertEqual(proposal.to_goal_review_proposal().action, GoalReviewAction.REPRIORITIZE)

    def test_success_resets_failure_streak(self):
        self.fail_plan("p1", 2)
        execution_id = "success:step:0"
        self.executions.start(execution_id, "npc", 10, "attempt", {"ready"}, {}, plan_actions=("attempt",))
        record = self.executions.advance(execution_id, 11, {"ready"}, {})
        self.evaluations.evaluate(record.execution_id)
        self.evaluations.register_plan("success", "npc", "goal", ("attempt",), {"done"})
        self.evaluations.evaluate_plan("success", "completed")
        self.fail_plan("p2", 20)
        self.assertEqual(self.evaluator(failures=2, window=1).assess(), ())

if __name__ == "__main__":
    unittest.main()
