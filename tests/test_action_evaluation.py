"""Tests for evidence-grounded action outcome evaluation."""
import unittest

from simreality.action_execution import ActionExecutionLedger, ActionExecutionPolicy
from simreality.action_evaluation import ActionPlanEvaluationLedger
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
        result = self.evaluations.evaluate("repair-extra")
        self.assertEqual(result.observed_added_facts, ("fixed", "safe"))
        snapshot = self.evaluations.to_snapshot()
        restored = ActionPlanEvaluationLedger.from_snapshot(self.executions, self.events, snapshot)
        self.assertEqual(restored.to_snapshot(), snapshot)

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
