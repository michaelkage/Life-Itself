"""Regression tests for bounded deterministic symbolic planning."""
import unittest

from simreality.planning import DeterministicPlanner, PlanningAction


class DeterministicPlannerTests(unittest.TestCase):
    def test_finds_least_cost_plan_not_merely_fewest_actions(self):
        planner = DeterministicPlanner([
            PlanningAction("quick-expensive", frozenset({"start"}), frozenset({"goal"}), cost=9),
            PlanningAction("step-one", frozenset({"start"}), frozenset({"middle"}), cost=2),
            PlanningAction("step-two", frozenset({"middle"}), frozenset({"goal"}), cost=2),
        ])
        result = planner.plan({"start"}, {"goal"})
        self.assertTrue(result.success)
        self.assertEqual(result.actions, ("step-one", "step-two"))
        self.assertEqual(result.total_cost, 4)

    def test_stable_action_id_tie_break(self):
        planner = DeterministicPlanner([
            PlanningAction("z-route", frozenset({"start"}), frozenset({"goal"})),
            PlanningAction("a-route", frozenset({"start"}), frozenset({"goal"})),
        ])
        self.assertEqual(planner.plan({"start"}, {"goal"}).actions, ("a-route",))

    def test_preconditions_and_delete_effects_are_respected(self):
        planner = DeterministicPlanner([
            PlanningAction("unlock", frozenset({"key"}), frozenset({"door-open"})),
            PlanningAction("enter", frozenset({"door-open"}), frozenset({"inside"})),
            PlanningAction("consume-key", frozenset({"key"}), frozenset({"used-key"}), frozenset({"key"})),
        ])
        result = planner.plan({"key"}, {"inside"})
        self.assertEqual(result.actions, ("unlock", "enter"))
        self.assertNotIn("consume-key", result.actions)

    def test_unsatisfied_preconditions_do_not_invent_actions(self):
        planner = DeterministicPlanner([
            PlanningAction("enter", frozenset({"door-open"}), frozenset({"inside"})),
        ])
        result = planner.plan({"outside"}, {"inside"})
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "no valid plan found")

    def test_already_satisfied_goal_returns_empty_plan(self):
        result = DeterministicPlanner([]).plan({"safe"}, {"safe"})
        self.assertTrue(result.success)
        self.assertEqual(result.actions, ())
        self.assertEqual(result.expanded_states, 0)

    def test_expansion_budget_is_bounded_and_validated(self):
        planner = DeterministicPlanner([
            PlanningAction("a", frozenset({"start"}), frozenset({"one"})),
            PlanningAction("b", frozenset({"one"}), frozenset({"goal"})),
        ])
        result = planner.plan({"start"}, {"goal"}, max_expansions=1)
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "expansion budget exhausted")
        with self.assertRaises(ValueError):
            planner.plan({"start"}, {"goal"}, max_expansions=0)

    def test_invalid_actions_and_duplicate_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            DeterministicPlanner([PlanningAction("bad", frozenset(), frozenset(), cost=0)])
        with self.assertRaises(ValueError):
            DeterministicPlanner([
                PlanningAction("same", frozenset(), frozenset()),
                PlanningAction("same", frozenset(), frozenset()),
            ])
        with self.assertRaises(ValueError):
            PlanningAction("bad", frozenset({"x"}), frozenset({"x"}), frozenset({"x"})).validate()


if __name__ == "__main__":
    unittest.main()
