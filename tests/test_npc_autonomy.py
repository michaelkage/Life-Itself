"""Regression tests for the integrated deterministic NPC decision cycle."""
import unittest

from simreality.goals import GoalBook, NPCGoal
from simreality.npc_autonomy import NPCDecisionCycle
from simreality.planning import DeterministicPlanner, PlanningAction


class NPCDecisionCycleTests(unittest.TestCase):
    def setUp(self):
        self.goals = GoalBook()
        self.goals.add(NPCGoal("rent", "npc-1", "security", priority=9))
        self.goals.add(NPCGoal("hobby", "npc-1", "creative", priority=2))
        self.planner = DeterministicPlanner([
            PlanningAction("work-shift", frozenset({"available"}),
                           frozenset({"earned-wages"})),
            PlanningAction("pay-rent", frozenset({"earned-wages"}),
                           frozenset({"rent-paid"})),
        ])
        self.cycle = NPCDecisionCycle(self.goals, self.planner)

    def test_selects_highest_priority_goal_and_plans_toward_explicit_facts(self):
        result = self.cycle.decide(
            "npc-1", 4, {"available"},
            {"rent": {"rent-paid"}, "hobby": {"relaxed"}},
        )
        self.assertTrue(result.actionable)
        self.assertEqual(result.goal_id, "rent")
        self.assertEqual(result.goal_category, "security")
        self.assertEqual(result.plan.actions, ("work-shift", "pay-rent"))

    def test_missing_goal_mapping_is_reported_not_guessed(self):
        result = self.cycle.decide("npc-1", 4, {"available"}, {})
        self.assertFalse(result.actionable)
        self.assertEqual(result.goal_id, "rent")
        self.assertIsNone(result.plan)
        self.assertIn("no desired-facts mapping", result.reason)

    def test_no_actionable_goal_returns_structured_idle_decision(self):
        result = self.cycle.decide("unknown-npc", 0, set(), {})
        self.assertFalse(result.actionable)
        self.assertIsNone(result.goal_id)
        self.assertEqual(result.reason, "no actionable goal")

    def test_unplannable_goal_is_not_reported_as_actionable(self):
        result = self.cycle.decide("npc-1", 0, {"available"},
                                   {"rent": {"impossible"}})
        self.assertFalse(result.actionable)
        self.assertEqual(result.goal_id, "rent")
        self.assertFalse(result.plan.success)
        self.assertIn("no valid plan", result.reason)

    def test_decision_cycle_does_not_mutate_goal_or_world_state(self):
        before = self.goals.snapshot()
        world = {"available"}
        world_before = set(world)
        self.cycle.decide("npc-1", 0, world, {"rent": {"rent-paid"}})
        self.assertEqual(self.goals.snapshot(), before)
        self.assertEqual(world, world_before)

    def test_repeat_decision_is_deterministic(self):
        args = ("npc-1", 3, {"available"}, {"rent": {"rent-paid"}})
        self.assertEqual(self.cycle.decide(*args), self.cycle.decide(*args))

    def test_invalid_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            self.cycle.decide(" ", 0, set(), {})
        with self.assertRaises(ValueError):
            self.cycle.decide("npc-1", -1, set(), {})


    def test_falls_back_to_lower_ranked_goal_when_top_goal_is_unplannable(self):
        result = self.cycle.decide(
            "npc-1", 4, {"available"},
            {"rent": {"impossible"}, "hobby": {"available"}},
        )
        self.assertTrue(result.actionable)
        self.assertEqual(result.goal_id, "hobby")
        self.assertIn("feasible fallback", result.reason)
        self.assertIn("rent", result.reason)

    def test_falls_back_when_top_goal_has_no_mapping(self):
        result = self.cycle.decide(
            "npc-1", 4, {"available"}, {"hobby": {"available"}}
        )
        self.assertTrue(result.actionable)
        self.assertEqual(result.goal_id, "hobby")
        self.assertIn("rent", result.reason)


if __name__ == "__main__":
    unittest.main()
