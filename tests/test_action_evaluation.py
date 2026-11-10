"""Tests for evidence-grounded action outcome evaluation."""
import unittest

from simreality.action_execution import ActionExecutionLedger, ActionExecutionPolicy
from simreality.action_evaluation import ActionPlanEvaluationLedger
from simreality.goals import GoalBook, NPCGoal
from simreality.npc_action_replanning import NPCActionReplanningCoordinator
from simreality.npc_autonomy import NPCDecisionCycle
from simreality.planning import DeterministicPlanner, PlanningAction
from simreality.world_events import WorldEventLedger


class ActionEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.events = WorldEventLedger()
        self.planner = DeterministicPlanner((
            PlanningAction("repair", frozenset({"broken"}), frozenset({"fixed", "safe"})),
            PlanningAction("inspect", frozenset({"fixed"}), frozenset({"inspected"})),
        ))
        self.policies = (ActionExecutionPolicy("repair", (("parts", 2.0),), 2),)
        self.executions = ActionExecutionLedger(self.planner, self.policies, self.events)
        self.evaluations = ActionPlanEvaluationLedger(self.executions, learning_min_samples=2)

    def test_completed_effect_resources_and_duration_are_compared(self):
        facts, resources = {"broken"}, {"parts": 5.0}
        self.executions.start("repair-1", "npc", 1, "repair", facts, resources,
                              plan_actions=("repair",))
        record = self.executions.advance("repair-1", 2, facts, resources)
        record = self.executions.advance("repair-1", 3, facts, resources)
        result = self.evaluations.evaluate(record.execution_id)
        self.assertEqual(result.observed_added_facts, ("fixed", "safe"))
        self.assertEqual(result.expected_resource_costs, (("parts", 2.0),))
        self.assertEqual(result.observed_duration_ticks, 2)
        self.assertEqual(result.deviation_flags, ())

    def test_evaluation_is_replay_safe_and_learning_waits_for_minimum_samples(self):
        facts, resources = {"broken"}, {"parts": 5.0}
        self.executions.execute("repair-once", "npc", 1, "repair", facts, resources,
                                plan_actions=("repair",))
        first = self.evaluations.evaluate("repair-once")
        self.assertIsNone(self.evaluations.reliability("repair"))
        self.assertEqual(first, self.evaluations.evaluate("repair-once"))
        self.executions.execute("repair-twice", "npc", 2, "repair", facts, resources,
                                plan_actions=("repair",))
        self.evaluations.evaluate("repair-twice")
        self.assertIsNotNone(self.evaluations.reliability("repair"))

    def test_evaluation_snapshot_roundtrip_preserves_history(self):
        facts, resources = {"broken"}, {"parts": 5.0}
        self.executions.start("repair-extra", "npc", 1, "repair", facts, resources,
                              plan_actions=("repair",))
        self.executions.advance("repair-extra", 2, facts, resources)
        self.executions.advance("repair-extra", 3, facts, resources)
        result = self.evaluations.evaluate("repair-extra")
        self.assertEqual(result.observed_added_facts, ("fixed", "safe"))
        snapshot = self.evaluations.to_snapshot()
        restored = ActionPlanEvaluationLedger.from_snapshot(self.executions, self.events, snapshot)
        self.assertEqual(restored.to_snapshot(), snapshot)

    def test_replanning_progression_attaches_terminal_evaluation(self):
        goals = GoalBook()
        goals.add(NPCGoal("fix-goal", "npc", "maintenance", 5.0))
        cycle = NPCDecisionCycle(goals, self.planner)
        coordinator = NPCActionReplanningCoordinator(
            cycle, self.executions, self.events, self.evaluations,
        )
        facts, resources = {"broken"}, {"parts": 5.0}
        planned = coordinator.replan(
            "npc", 1, facts, resources, {"fix-goal": {"fixed"}},
            reason="repair required",
        )
        coordinator.advance(planned.execution_id, 2, facts, resources,
                            {"fix-goal": {"fixed"}})
        progression = coordinator.advance(
            planned.execution_id, 3, facts, resources, {"fix-goal": {"fixed"}},
        )
        self.assertIsNotNone(progression.evaluation)
        self.assertEqual(progression.evaluation.execution_id, planned.execution_id)


    def test_multi_step_plan_evaluation_checks_final_goal(self):
        planner = DeterministicPlanner((
            PlanningAction("gather", frozenset({"at-site"}), frozenset({"materials"})),
            PlanningAction("build", frozenset({"materials"}), frozenset({"shelter"})),
        ))
        events = WorldEventLedger()
        executions = ActionExecutionLedger(planner, (), events)
        evaluations = ActionPlanEvaluationLedger(executions, learning_min_samples=1)
        goals = GoalBook()
        goals.add(NPCGoal("shelter-goal", "npc", "survival", 9.0))
        coordinator = NPCActionReplanningCoordinator(
            NPCDecisionCycle(goals, planner), executions, events, evaluations,
        )
        facts, resources = {"at-site"}, {}
        goal_facts = {"shelter-goal": {"shelter"}}
        plan = coordinator.replan(
            "npc", 1, facts, resources, goal_facts, reason="needs shelter",
        )
        first = coordinator.advance(plan.execution_id, 2, facts, resources, goal_facts)
        self.assertIsNotNone(first.next_active)
        second = coordinator.advance(first.next_active.execution_id, 3, facts, resources, goal_facts)
        self.assertEqual(second.plan_evaluation.terminal_status, "completed")
        self.assertEqual(second.plan_evaluation.expected_goal_facts, ("shelter",))
        self.assertEqual(second.plan_evaluation.observed_goal_facts, ("shelter",))
        self.assertEqual(second.plan_evaluation.missing_goal_facts, ())
        self.assertEqual(second.plan_evaluation.completed_actions, ("gather", "build"))

    def test_plan_evaluation_records_goal_failure_after_interruption(self):
        planner = DeterministicPlanner((
            PlanningAction("gather", frozenset({"at-site"}), frozenset({"materials"})),
            PlanningAction("build", frozenset({"materials"}), frozenset({"shelter"})),
        ))
        events = WorldEventLedger()
        executions = ActionExecutionLedger(planner, (), events)
        evaluations = ActionPlanEvaluationLedger(executions)
        goals = GoalBook()
        goals.add(NPCGoal("shelter-goal", "npc", "survival", 9.0))
        coordinator = NPCActionReplanningCoordinator(
            NPCDecisionCycle(goals, planner), executions, events, evaluations,
        )
        facts, resources = {"at-site"}, {}
        goal_facts = {"shelter-goal": {"shelter"}}
        plan = coordinator.replan("npc", 1, facts, resources, goal_facts, reason="build shelter")
        progression = coordinator.advance(
            plan.execution_id, 2, facts, resources, goal_facts,
            interruption="storm stopped work",
        )
        self.assertEqual(progression.plan_evaluation.terminal_status, "failed")
        self.assertEqual(progression.plan_evaluation.missing_goal_facts, ("shelter",))
        self.assertIn("goal_not_achieved", progression.plan_evaluation.deviation_flags)

    def test_cancelled_action_is_recorded_as_non_success(self):
        facts, resources = {"broken"}, {"parts": 5.0}
        self.executions.start("cancel-me", "npc", 1, "repair", facts, resources,
                              plan_actions=("repair",))
        self.executions.cancel("cancel-me", 2, "operator cancelled")
        result = self.evaluations.evaluate("cancel-me")
        self.assertIn("cancelled", result.deviation_flags)
        self.assertEqual(result.expected_added_facts, ())


if __name__ == "__main__":
    unittest.main()
