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


    def test_learned_reliability_breaks_equal_cost_ties_without_rewriting_base_costs(self):
        planner = DeterministicPlanner([
            PlanningAction("a-unreliable", frozenset({"start"}), frozenset({"goal"}), cost=2),
            PlanningAction("z-reliable", frozenset({"start"}), frozenset({"goal"}), cost=2),
        ])
        baseline = planner.plan({"start"}, {"goal"})
        learned = planner.plan(
            {"start"}, {"goal"},
            action_reliability={"a-unreliable": 0.0, "z-reliable": 1.0},
        )
        self.assertEqual(baseline.actions, ("a-unreliable",))
        self.assertEqual(learned.actions, ("z-reliable",))
        self.assertEqual(planner.actions["a-unreliable"].cost, 2)
        self.assertEqual(planner.actions["z-reliable"].cost, 2)

    def test_reliability_input_is_validated(self):
        planner = DeterministicPlanner([
            PlanningAction("go", frozenset({"start"}), frozenset({"goal"})),
        ])
        with self.assertRaises(ValueError):
            planner.plan({"start"}, {"goal"}, action_reliability={"unknown": 0.8})
        with self.assertRaises(ValueError):
            planner.plan({"start"}, {"goal"}, action_reliability={"go": 1.1})

    def test_preconditions_are_respected(self):
        planner = DeterministicPlanner([
            PlanningAction("unlock", frozenset({"key"}), frozenset({"door-open"})),
            PlanningAction("enter", frozenset({"door-open"}), frozenset({"inside"})),
            PlanningAction("consume-key", frozenset({"key"}), frozenset({"used-key"}), frozenset({"key"})),
        ])
        result = planner.plan({"key"}, {"inside"})
        self.assertEqual(result.actions, ("unlock", "enter"))

    def test_delete_effects_change_the_planning_state(self):
        planner = DeterministicPlanner([
            PlanningAction("use-last-key", frozenset({"key"}), frozenset({"door-open"}), frozenset({"key"})),
            PlanningAction("open-second-door", frozenset({"key", "door-open"}), frozenset({"second-open"})),
            PlanningAction("reach-room", frozenset({"door-open", "second-open"}), frozenset({"inside"})),
        ])
        result = planner.plan({"key"}, {"inside"})
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "no valid plan found")

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
