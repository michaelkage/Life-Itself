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


    def test_accepted_identity_goal_review_changes_the_next_planning_choice(self):
        from simreality.identity_decisions import IdentityChangeDecision
        from simreality.identity_goal_alignment import (
            IdentityGoalAction, IdentityGoalAlignmentAdapter,
            IdentityGoalAlignmentPolicy, IdentityGoalReviewDecision,
            IdentityGoalReviewDecisionLedger,
        )

        goals = GoalBook()
        goals.add(NPCGoal("career", "npc-1", "career", priority=5.0))
        goals.add(NPCGoal("security", "npc-1", "security", priority=6.0))
        planner = DeterministicPlanner([
            PlanningAction("advance-career", frozenset({"employed"}),
                           frozenset({"career-progress"})),
            PlanningAction("secure-home", frozenset({"employed"}),
                           frozenset({"home-secure"})),
        ])
        cycle = NPCDecisionCycle(goals, planner)
        goal_facts = {
            "career": {"career-progress"},
            "security": {"home-secure"},
        }

        before = cycle.decide("npc-1", 4, {"employed"}, goal_facts)
        self.assertEqual(before.goal_id, "security")

        identity_decision = IdentityChangeDecision(
            "identity-career-1", "event-career-1", "npc-1",
            "ambition-policy", "ambition", True, 4,
            "I now value professional growth", 0.0, 0.3, 0.3, 0.8,
            "participant",
        )
        adapter = IdentityGoalAlignmentAdapter(goals, (
            IdentityGoalAlignmentPolicy(
                "ambition-career", "ambition", "career",
                IdentityGoalAction.REPRIORITIZE,
                minimum_abs_delta=0.1, priority_delta=3.0,
            ),
        ))
        proposal, = adapter.assess((identity_decision,), current_tick=4)
        ledger = IdentityGoalReviewDecisionLedger()
        review = IdentityGoalReviewDecision(
            "career-review-1", proposal, True, 5,
            "This goal now matters more to me",
        )
        ledger.record(review)

        # Identity acceptance alone is insufficient; the separate goal review
        # must be accepted and applied before planning sees the new priority.
        self.assertEqual(cycle.decide("npc-1", 5, {"employed"}, goal_facts).goal_id,
                         "security")
        self.assertTrue(ledger.apply_accepted("career-review-1", goals))
        after = cycle.decide("npc-1", 5, {"employed"}, goal_facts)
        self.assertEqual(after.goal_id, "career")
        self.assertEqual(after.plan.actions, ("advance-career",))
        self.assertEqual(goals.goals["career"].priority, 8.0)

    def test_rejected_identity_goal_review_cannot_change_planning_choice(self):
        from simreality.identity_decisions import IdentityChangeDecision
        from simreality.identity_goal_alignment import (
            IdentityGoalAction, IdentityGoalAlignmentAdapter,
            IdentityGoalAlignmentPolicy, IdentityGoalReviewDecision,
            IdentityGoalReviewDecisionLedger,
        )

        goals = GoalBook()
        goals.add(NPCGoal("career", "npc-1", "career", priority=5.0))
        goals.add(NPCGoal("security", "npc-1", "security", priority=6.0))
        identity_decision = IdentityChangeDecision(
            "identity-career-2", "event-career-2", "npc-1",
            "ambition-policy", "ambition", True, 4,
            "I now value professional growth", 0.0, 0.3, 0.3, 0.8,
            "participant",
        )
        adapter = IdentityGoalAlignmentAdapter(goals, (
            IdentityGoalAlignmentPolicy(
                "ambition-career", "ambition", "career",
                IdentityGoalAction.REPRIORITIZE,
                minimum_abs_delta=0.1, priority_delta=3.0,
            ),
        ))
        proposal, = adapter.assess((identity_decision,), current_tick=4)
        ledger = IdentityGoalReviewDecisionLedger((
            IdentityGoalReviewDecision(
                "career-review-rejected", proposal, False, 5,
                "I want to keep my current priorities",
            ),
        ))
        planner = DeterministicPlanner([
            PlanningAction("advance-career", frozenset({"employed"}),
                           frozenset({"career-progress"})),
            PlanningAction("secure-home", frozenset({"employed"}),
                           frozenset({"home-secure"})),
        ])
        cycle = NPCDecisionCycle(goals, planner)
        before = cycle.decide(
            "npc-1", 5, {"employed"},
            {"career": {"career-progress"}, "security": {"home-secure"}},
        )
        with self.assertRaisesRegex(ValueError, "rejected"):
            ledger.apply_accepted("career-review-rejected", goals)
        after = cycle.decide(
            "npc-1", 5, {"employed"},
            {"career": {"career-progress"}, "security": {"home-secure"}},
        )
        self.assertEqual(before, after)
        self.assertEqual(after.goal_id, "security")


if __name__ == "__main__":
    unittest.main()
