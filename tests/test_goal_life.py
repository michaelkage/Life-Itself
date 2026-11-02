"""Regression tests for goal-aware, resource-bounded daily routine proposals."""
import unittest

from simreality.goals import GoalBook, NPCGoal
from simreality.goal_life import (
    GoalLifeAdapter, GoalLifeContext, GoalRoutinePolicy,
)
from simreality.routines import RoutineBlock, RoutineBook


class GoalLifeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.goals = GoalBook()
        self.goals.add(NPCGoal("business", "npc-1", "entrepreneurship",
                               priority=8, confidence=0.9))
        self.goals.add(NPCGoal("family", "npc-1", "family",
                               priority=5, confidence=1.0))
        self.routines = RoutineBook((
            RoutineBlock("market-research", "npc-1", "research",
                         "library", 600, 660, priority=0.3),
            RoutineBlock("family-dinner", "npc-1", "family_time",
                         "home", 1080, 1140, priority=0.8),
            RoutineBlock("unrelated", "npc-1", "sleep",
                         "home", 1320, 1439, priority=0.9),
            RoutineBlock("other-person", "npc-2", "research",
                         "library", 600, 660, priority=0.2),
        ))
        self.policies = (
            GoalRoutinePolicy("business-research", "entrepreneurship",
                              "research", priority_bonus=0.5,
                              time_cost_minutes=30, resource_cost=2.0),
            GoalRoutinePolicy("family-connection", "family",
                              "family_time", priority_bonus=0.3,
                              time_cost_minutes=20, resource_cost=0.0),
        )
        self.adapter = GoalLifeAdapter(self.goals, self.routines, self.policies)

    def test_goals_influence_matching_routines_only(self):
        result = self.adapter.assess(GoalLifeContext(
            "npc-1", 10, 60, 3.0, social_support=0.5,
        ))
        by_routine = {item.routine_id: item for item in result.proposals}
        self.assertTrue(by_routine["market-research"].accepted)
        self.assertGreater(by_routine["market-research"].proposed_priority, 0.3)
        self.assertTrue(by_routine["family-dinner"].accepted)
        self.assertGreater(by_routine["family-dinner"].proposed_priority, 0.8)
        self.assertNotIn("unrelated", by_routine)
        self.assertNotIn("other-person", by_routine)
        self.assertEqual(result.remaining_minutes, 10)
        self.assertEqual(result.remaining_resources, 1.0)

    def test_daily_budget_is_allocated_in_goal_priority_order(self):
        result = self.adapter.assess(GoalLifeContext(
            "npc-1", 10, 30, 2.0,
        ))
        by_routine = {item.routine_id: item for item in result.proposals}
        self.assertTrue(by_routine["market-research"].accepted)
        self.assertFalse(by_routine["family-dinner"].accepted)
        self.assertEqual(by_routine["family-dinner"].reason,
                         "insufficient discretionary time")
        self.assertEqual(result.remaining_minutes, 0)
        self.assertEqual(result.remaining_resources, 0.0)

    def test_life_pressure_reduces_goal_influence(self):
        supported = self.adapter.assess(GoalLifeContext(
            "npc-1", 10, 60, 3.0, social_support=1.0,
        ))
        pressured = self.adapter.assess(GoalLifeContext(
            "npc-1", 10, 60, 3.0, stress=1.0,
            obligation_load=1.0, recent_setbacks=1.0,
        ))
        supported_boost = next(p for p in supported.proposals
                               if p.routine_id == "market-research")
        pressured_boost = next(p for p in pressured.proposals
                               if p.routine_id == "market-research")
        self.assertGreater(supported_boost.proposed_priority,
                           pressured_boost.proposed_priority)
        self.assertEqual(pressured_boost.life_capacity, 0.15)

    def test_insufficient_resources_do_not_create_a_routine_boost(self):
        result = self.adapter.assess(GoalLifeContext(
            "npc-1", 10, 60, 1.0,
        ))
        proposal = next(p for p in result.proposals
                        if p.routine_id == "market-research")
        self.assertFalse(proposal.accepted)
        self.assertEqual(proposal.proposed_priority, proposal.baseline_priority)
        self.assertEqual(proposal.reason, "insufficient available resources")

    def test_assessment_is_deterministic_and_does_not_mutate_inputs(self):
        before_goals = self.goals.snapshot()
        before_routines = self.routines.snapshot()
        context = GoalLifeContext("npc-1", 10, 60, 3.0)
        first = self.adapter.assess(context)
        second = self.adapter.assess(context)
        self.assertEqual(first, second)
        self.assertEqual(self.goals.snapshot(), before_goals)
        self.assertEqual(self.routines.snapshot(), before_routines)

    def test_low_confidence_goal_is_not_mapped_to_a_routine(self):
        self.policies = (GoalRoutinePolicy(
            "high-confidence", "entrepreneurship", "research",
            minimum_confidence=0.95,
        ),)
        adapter = GoalLifeAdapter(self.goals, self.routines, self.policies)
        result = adapter.assess(GoalLifeContext("npc-1", 10, 60, 3.0))
        self.assertEqual(result.proposals, ())

    def test_duplicate_policy_ids_and_invalid_context_are_rejected(self):
        duplicate = self.policies + (self.policies[0],)
        with self.assertRaisesRegex(ValueError, "unique"):
            GoalLifeAdapter(self.goals, self.routines, duplicate)
        with self.assertRaises(ValueError):
            GoalLifeContext("npc-1", 0, -1, 0.0)
        with self.assertRaises(ValueError):
            GoalLifeContext("npc-1", 0, 10, 0.0, stress=1.1)


if __name__ == "__main__":
    unittest.main()
